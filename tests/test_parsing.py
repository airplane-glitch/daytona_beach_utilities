"""All sample values here are made up."""
import json
from datetime import date

import pytest

from dbu import parsing as p


def test_unwrap_peels_double_encoded_json():
    inner = {"a": 1}
    assert p.unwrap(json.dumps(json.dumps(inner))) == inner
    assert p.unwrap(json.dumps(inner)) == inner


def test_unwrap_rejects_a_web_page():
    with pytest.raises(ValueError):
        p.unwrap("<html>please sign in</html>")


@pytest.mark.parametrize(
    "raw,expected",
    [("$168.21", 168.21), ("-$0.83", -0.83), ("($0.83)", -0.83), ("$0.00 ", 0.0), ("$1,234.50", 1234.5), (12, 12.0), ("", None), (None, None), ("n/a", None)],
)
def test_parse_money(raw, expected):
    assert p.parse_money(raw) == expected


def test_dates():
    assert p.parse_long_date("November 02, 2026") == date(2026, 11, 2)
    assert p.parse_long_date(None) is None
    assert p.parse_iso_date("2026-10-23T00:00:00") == date(2026, 10, 23)
    assert p.parse_iso_date("0001-01-01T00:00:00") is None


def test_split_account_and_address():
    acct = p.split_account("00000001-01|dG9rZW4x|dG9rZW4y|Active|100")
    assert acct["number"] == "00000001-01" and acct["token"] == "dG9rZW4x" and acct["status"] == "Active"
    assert p.tidy_address("100 EXAMPLE ST  DOM  ") == "100 Example St"
    assert p.tidy_address("5 SAMPLE WAY") == "5 Sample Way"


def test_bills_sorted_newest_first():
    bills = p.parse_bills(
        {
            "bills": [
                {"billNumber": 1, "billDate": "2026-09-18T00:00:00", "currentTransactions": 134.11, "previousBilling": 0, "amountDueBeforeDueDate": 134.11, "usage": 5.7},
                {"billNumber": 2, "billDate": "2026-10-23T00:00:00", "currentTransactions": 168.21, "previousBilling": -0.83, "amountDueBeforeDueDate": 167.38, "usage": 8.88},
                {"billNumber": 3, "billDate": "0001-01-01T00:00:00"},
            ]
        }
    )
    assert [b["number"] for b in bills] == [2, 1]
    assert bills[0]["usage"] == 8.88


def test_detail_sums_services_and_handles_nesting():
    rows = [
        [{"ARCode": "WATER     ", "Amount": 50.0}, {"ARCode": "SEWER", "Amount": 30.0}],
        [{"ARCode": "GARBAGE", "Amount": 20.0}, {"ARCode": "WATER", "Amount": 1.5}, {"ARCode": "NEW FEE", "Amount": 2.0}],
    ]
    assert p.parse_detail(rows) == {"water": 51.5, "sewer": 30.0, "garbage": 20.0, "new_fee": 2.0}


def test_summary():
    s = p.parse_summary(
        {"dueDateString": "November 02, 2026", "billDateString": "October 23, 2026", "currentBalanceString": "$168.21", "pastBalanceString": "-$0.83", "totalBalanceString": "$0.00 "}
    )
    assert s == {"amount_due": 0.0, "current_charges": 168.21, "previous_balance": -0.83, "due_date": date(2026, 11, 2), "bill_date": date(2026, 10, 23)}
