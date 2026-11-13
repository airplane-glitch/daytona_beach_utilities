"""Pure helpers that turn the portal's JSON into plain Python values. No Home Assistant imports, so they are easy to test."""
from __future__ import annotations

import json
import re
from datetime import date, datetime
from typing import Any

# Friendly keys for the service codes that appear on a bill. Any other code is kept under its lower-case code.
SERVICE_KEYS = {
    "WATER": "water",
    "SEWER": "sewer",
    "GARBAGE": "garbage",
    "STORMWATER": "stormwater",
    "TAX": "tax",
}


def unwrap(text: str) -> Any:
    """The portal often returns JSON that is itself wrapped in a JSON string. Peel it until it is a list or dict."""
    value: Any = text
    for _ in range(4):
        if not isinstance(value, str):
            break
        try:
            value = json.loads(value)
        except ValueError:
            break
    if not isinstance(value, (dict, list)):
        raise ValueError("unexpected response from the portal")
    return value


def parse_money(value: Any) -> float | None:
    """'$168.21', '-$0.83', '($0.83)', 168.21 -> float. Empty or missing -> None."""
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value).strip()
    if not text:
        return None
    negative = text.startswith("-") or (text.startswith("(") and text.endswith(")"))
    digits = re.sub(r"[^0-9.]", "", text)
    if not digits or digits == ".":
        return None
    number = float(digits)
    return -number if negative else number


def parse_long_date(value: Any) -> date | None:
    """'November 02, 2026' -> date."""
    if not value:
        return None
    text = str(value).strip()
    for fmt in ("%B %d, %Y", "%b %d, %Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(text, fmt).date()
        except ValueError:
            continue
    return None


def parse_iso_date(value: Any) -> date | None:
    """'2026-10-23T00:00:00' -> date. The portal's 'no date' value (year 1) -> None."""
    if not value:
        return None
    try:
        parsed = date.fromisoformat(str(value)[:10])
    except ValueError:
        return None
    return None if parsed.year < 1990 else parsed


def split_account(raw: str) -> dict[str, str]:
    """The account selector lists accounts as 'number|token|token|status|street number'."""
    parts = raw.split("|")
    parts += [""] * (5 - len(parts))
    return {"number": parts[0], "token": parts[1], "status": parts[3] or "Unknown", "raw": raw}


def tidy_address(value: str) -> str:
    """'100 EXAMPLE ST  DOM  ' -> '100 Example St'."""
    words = value.split()
    if words and words[-1].upper() in ("DOM", "COM"):
        words = words[:-1]
    return " ".join(words).title()


def parse_bills(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Billing history, newest first."""
    bills = []
    for item in payload.get("bills") or []:
        bill_date = parse_iso_date(item.get("billDate"))
        if bill_date is None:
            continue
        bills.append(
            {
                "number": item.get("billNumber"),
                "date": bill_date,
                "charges": parse_money(item.get("currentTransactions")),
                "previous": parse_money(item.get("previousBilling")),
                "due": parse_money(item.get("amountDueBeforeDueDate")),
                "usage": parse_money(item.get("usage")),
            }
        )
    bills.sort(key=lambda b: b["date"], reverse=True)
    return bills


def parse_detail(payload: Any) -> dict[str, float]:
    """One bill's line items -> amount per service. The portal nests the list one level deep."""
    lines: list[dict[str, Any]] = []
    stack = payload if isinstance(payload, list) else [payload]
    while stack:
        item = stack.pop(0)
        if isinstance(item, list):
            stack = item + stack
        elif isinstance(item, dict):
            lines.append(item)
    totals: dict[str, float] = {}
    for line in lines:
        code = str(line.get("ARCode") or "").strip().upper()
        amount = parse_money(line.get("Amount"))
        if not code or amount is None:
            continue
        key = SERVICE_KEYS.get(code, re.sub(r"[^a-z0-9]+", "_", code.lower()).strip("_"))
        totals[key] = round(totals.get(key, 0.0) + amount, 2)
    return totals


def parse_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "amount_due": parse_money(payload.get("totalBalanceString")),
        "current_charges": parse_money(payload.get("currentBalanceString")),
        "previous_balance": parse_money(payload.get("pastBalanceString")),
        "due_date": parse_long_date(payload.get("dueDateString")),
        "bill_date": parse_long_date(payload.get("billDateString")),
    }
