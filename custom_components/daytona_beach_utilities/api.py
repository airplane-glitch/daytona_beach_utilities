"""Client for the City of Daytona Beach customer portal (https://cc.codb.us).

The portal has no public API. This client does what the website's own pages do: sign in with the account's
username and password, then read the same JSON feeds the billing pages read. It only reads; it never pays or changes anything.
"""
from __future__ import annotations

import asyncio
import logging
from datetime import date, timedelta
from typing import Any

import aiohttp

from .parsing import (
    parse_bills,
    parse_detail,
    parse_summary,
    split_account,
    tidy_address,
    unwrap,
)

_LOGGER = logging.getLogger(__name__)

BASE_URL = "https://cc.codb.us"
API_URL = f"{BASE_URL}/API/AdvancedUtility"
TIMEOUT = aiohttp.ClientTimeout(total=45)
HEADERS = {"Accept": "application/json, text/plain, */*", "X-Requested-With": "XMLHttpRequest"}


class PortalError(Exception):
    """The portal could not be reached or answered with something unexpected."""


class AuthError(PortalError):
    """The username or password was not accepted."""


class DaytonaPortal:
    """One signed-in session. The portal keeps the 'selected account' in the session, so accounts are read one at a time."""

    def __init__(self, session: aiohttp.ClientSession, username: str, password: str) -> None:
        self._session = session
        self._username = username
        self._password = password
        self._lock = asyncio.Lock()

    async def _request(self, method: str, path: str, **kwargs: Any) -> str:
        try:
            # Never follow redirects: a redirect could otherwise carry the sign-in (and its password) to another host.
            async with self._session.request(
                method, f"{API_URL}/{path}", headers=HEADERS, timeout=TIMEOUT, allow_redirects=False, **kwargs
            ) as resp:
                text = await resp.text()
                status = resp.status
        except (aiohttp.ClientError, asyncio.TimeoutError) as err:
            raise PortalError(f"cannot reach the portal: {type(err).__name__}") from err
        if 300 <= status < 400:
            # The portal sends signed-out visitors to its sign-in page.
            raise AuthError("the portal redirected the request (signed out?)")
        if status in (401, 403):
            raise AuthError("the portal refused the request")
        if status >= 500 and path.startswith("LinkAPI/security/login"):
            raise AuthError("the portal rejected the sign-in")
        if status >= 400:
            raise PortalError(f"the portal answered with status {status}")
        return text

    async def _get_json(self, path: str, **params: Any) -> Any:
        text = await self._request("GET", path, params=params or None)
        try:
            return unwrap(text)
        except ValueError as err:
            # An expired or missing session comes back as a web page, not JSON.
            raise AuthError("the portal did not return data (signed out?)") from err

    async def login(self) -> None:
        """Sign in. The result is a session cookie held by the aiohttp session."""
        await self._request(
            "POST",
            "LinkAPI/security/login",
            data={"username": self._username, "password": self._password, "defaultAccount": ""},
        )

    async def accounts(self) -> tuple[str, list[dict[str, str]]]:
        """The customer number and every account on the login: {number, token, status, raw, address}."""
        data = await self._get_json("AccountSelector/selector/criteria")
        customer = str(data.get("customer") or "")
        raws = data.get("accounts") or []
        addresses = data.get("addresses") or []
        if not customer or not raws:
            raise AuthError("the login has no accounts")
        accounts = []
        for index, raw in enumerate(raws):
            account = split_account(raw)
            account["address"] = tidy_address(addresses[index]) if index < len(addresses) else account["number"]
            accounts.append(account)
        return customer, accounts

    async def _read_account(self, customer: str, account: dict[str, str]) -> dict[str, Any]:
        # Select the account for this session first, otherwise the portal answers for whichever one was selected before.
        # The portal answers this one with the bare word "Success", which is not an object, so the body is not parsed.
        await self._request(
            "GET", "AccountSelector/selector/setcustomeraccountsessions", params={"accountNumber": account["raw"]}
        )
        summary = parse_summary(await self._get_json("BillingSummary/summary/data", custno=customer, acctno=account["token"]))
        today = date.today()
        history = await self._get_json(
            "BillingHistory/billinghistory/billinghistorybydates",
            customernumber=customer,
            accountnumber=account["token"],
            startdate=(today - timedelta(days=400)).strftime("%m/%d/%Y"),
            enddate=(today + timedelta(days=1)).strftime("%m/%d/%Y"),
        )
        bills = parse_bills(history)
        charges: dict[str, float] = {}
        if bills and bills[0]["number"]:
            try:
                charges = parse_detail(
                    await self._get_json(
                        "BillingHistory/billinghistory/GetBillDetail",
                        customernumber=customer,
                        accountnumber=account["token"],
                        billnumbers=bills[0]["number"],
                        billdates=bills[0]["date"].strftime("%m/%d/%Y"),
                    )
                )
            except PortalError as err:
                _LOGGER.debug("Bill detail not available: %s", err)
        latest = bills[0] if bills else {}
        return {
            "id": account["number"],
            "address": account["address"],
            "status": account["status"],
            **summary,
            "bill_date": summary["bill_date"] or latest.get("date"),
            "usage": latest.get("usage"),
            "charges": charges,
            "bills": bills,
        }

    async def fetch_all(self) -> dict[str, dict[str, Any]]:
        """Sign in and read every account on the login. Returns {account number: data}."""
        async with self._lock:
            await self.login()
            customer, accounts = await self.accounts()
            result: dict[str, dict[str, Any]] = {}
            for account in accounts:
                try:
                    result[account["number"]] = await self._read_account(customer, account)
                except AuthError:
                    raise
                except PortalError as err:
                    _LOGGER.warning("Could not read one of the accounts: %s", err)
            if not result:
                raise PortalError("none of the accounts could be read")
            return result
