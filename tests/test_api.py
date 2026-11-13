"""Runs the client against a small fake portal. All accounts, names and amounts are made up.

The fake portal behaves like the real one in the way that matters most: it answers for whichever account was
selected last in the session, so the client has to select each account before reading it.
"""
import json
from datetime import date

import aiohttp
import pytest
from aiohttp import web

from dbu import api as api_module
from dbu.api import AuthError, DaytonaPortal, PortalError

ACCOUNTS = ["00000001-01|dG9rZW4x|dGlja2V0MQ==|Active|100", "00000002-01|dG9rZW4y|dGlja2V0Mg==|Active|200"]
DATA = {
    "00000001-01": {"due": "November 02, 2026", "total": "$0.00", "cur": "$100.00", "bills": [(date(2026, 10, 23), 100.0, 8.5)], "lines": {"WATER": 40.0, "SEWER": 50.0, "TAX": 10.0}},
    "00000002-01": {"due": "November 16, 2026", "total": "$55.55", "cur": "$55.55", "bills": [(date(2026, 11, 6), 55.55, 0.4), (date(2026, 10, 6), 50.0, 0.3)], "lines": {"WATER": 5.0, "GARBAGE": 30.0, "STORMWATER": 20.55}},
}


def wrap(obj):
    return web.Response(text=json.dumps(json.dumps(obj)), content_type="application/json")


def make_app(good_password="pw"):
    state = {"selected": {}}
    app = web.Application()

    async def login(request):
        form = await request.post()
        if form.get("password") != good_password:
            return web.Response(status=500, text="nope")
        resp = web.Response(text="ok")
        resp.set_cookie("sid", "s1")
        return resp

    def signed_in(request):
        return request.cookies.get("sid") == "s1"

    async def criteria(request):
        if not signed_in(request):
            return web.Response(text="<html>sign in</html>", content_type="text/html")
        return wrap({"customer": "999", "accounts": ACCOUNTS, "addresses": ["100 EXAMPLE ST  DOM  ", "200 SAMPLE WAY  DOM  "]})

    async def select(request):
        state["selected"]["sid"] = request.query["accountNumber"].split("|")[0]
        # The real portal answers with the bare JSON string "Success", not an object.
        return web.Response(text=json.dumps("Success"), content_type="application/json")

    def current():
        return DATA[state["selected"]["sid"]]

    async def summary(request):
        d = current()
        return wrap({"dueDateString": d["due"], "billDateString": d["bills"][0][0].strftime("%B %d, %Y"), "currentBalanceString": d["cur"], "pastBalanceString": "$0.00", "totalBalanceString": d["total"]})

    async def history(request):
        d = current()
        return wrap({"bills": [{"billNumber": 100 + i, "billDate": b[0].isoformat() + "T00:00:00", "currentTransactions": b[1], "previousBilling": 0, "amountDueBeforeDueDate": b[1], "usage": b[2]} for i, b in enumerate(d["bills"])]})

    async def detail(request):
        return wrap([[{"ARCode": k.ljust(10), "Amount": v} for k, v in current()["lines"].items()]])

    base = "/API/AdvancedUtility"
    app.router.add_post(f"{base}/LinkAPI/security/login", login)
    app.router.add_get(f"{base}/AccountSelector/selector/criteria", criteria)
    app.router.add_get(f"{base}/AccountSelector/selector/setcustomeraccountsessions", select)
    app.router.add_get(f"{base}/BillingSummary/summary/data", summary)
    app.router.add_get(f"{base}/BillingHistory/billinghistory/billinghistorybydates", history)
    app.router.add_get(f"{base}/BillingHistory/billinghistory/GetBillDetail", detail)
    return app


@pytest.fixture
async def server(aiohttp_server, monkeypatch):
    srv = await aiohttp_server(make_app())
    monkeypatch.setattr(api_module, "API_URL", f"http://{srv.host}:{srv.port}/API/AdvancedUtility")
    return srv


@pytest.mark.asyncio
async def test_reads_every_account_with_its_own_data(server):
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
        data = await DaytonaPortal(session, "someone", "pw").fetch_all()
    assert set(data) == {"00000001-01", "00000002-01"}
    one, two = data["00000001-01"], data["00000002-01"]
    assert one["address"] == "100 Example St" and two["address"] == "200 Sample Way"
    assert one["amount_due"] == 0.0 and two["amount_due"] == 55.55
    assert one["usage"] == 8.5 and two["usage"] == 0.4
    assert one["charges"] == {"water": 40.0, "sewer": 50.0, "tax": 10.0}
    assert two["charges"] == {"water": 5.0, "garbage": 30.0, "stormwater": 20.55}
    assert len(two["bills"]) == 2 and two["bills"][0]["date"] == date(2026, 11, 6)


@pytest.mark.asyncio
async def test_wrong_password_is_an_auth_error(server):
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
        with pytest.raises(AuthError):
            await DaytonaPortal(session, "someone", "wrong").fetch_all()


@pytest.mark.asyncio
async def test_unreachable_portal_is_a_portal_error(monkeypatch):
    monkeypatch.setattr(api_module, "API_URL", "http://127.0.0.1:1/API/AdvancedUtility")
    async with aiohttp.ClientSession(cookie_jar=aiohttp.CookieJar(unsafe=True)) as session:
        with pytest.raises(PortalError):
            await DaytonaPortal(session, "someone", "pw").fetch_all()
