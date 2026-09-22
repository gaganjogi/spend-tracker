from datetime import date, timedelta

import pytest


def test_create_expense_success(client):
    resp = client.post(
        "/expenses",
        json={"amount": 12.5, "category": "Food", "note": "lunch", "date": "2026-01-15"},
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["amount"] == "12.50"
    assert body["category"] == "food"
    assert body["note"] == "lunch"
    assert body["date"] == "2026-01-15"
    assert "id" in body
    assert "created_at" in body


@pytest.mark.parametrize("amount", [0, -5, -0.01])
def test_create_expense_rejects_non_positive_amount(client, amount):
    resp = client.post("/expenses", json={"amount": amount, "category": "food", "date": "2026-01-15"})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"


def test_create_expense_rejects_too_many_decimals(client):
    resp = client.post("/expenses", json={"amount": 12.555, "category": "food", "date": "2026-01-15"})
    assert resp.status_code == 422


@pytest.mark.parametrize("missing_field", ["amount", "category", "date"])
def test_create_expense_rejects_missing_required_field(client, missing_field):
    payload = {"amount": 10, "category": "food", "date": "2026-01-15"}
    del payload[missing_field]
    resp = client.post("/expenses", json=payload)
    assert resp.status_code == 422


@pytest.mark.parametrize("category", ["", "   "])
def test_create_expense_rejects_empty_or_whitespace_category(client, category):
    resp = client.post("/expenses", json={"amount": 10, "category": category, "date": "2026-01-15"})
    assert resp.status_code == 422


def test_create_expense_rejects_future_date(client):
    future = (date.today() + timedelta(days=1)).isoformat()
    resp = client.post("/expenses", json={"amount": 10, "category": "food", "date": future})
    assert resp.status_code == 422


def test_create_expense_rejects_bad_date_format(client):
    resp = client.post("/expenses", json={"amount": 10, "category": "food", "date": "15-01-2026"})
    assert resp.status_code == 422


def test_create_expense_normalizes_category(client):
    resp = client.post("/expenses", json={"amount": 10, "category": "  FOOD  ", "date": "2026-01-15"})
    assert resp.status_code == 201
    assert resp.json()["category"] == "food"


def test_create_expense_allows_max_two_decimals(client):
    resp = client.post("/expenses", json={"amount": 12.5, "category": "food", "date": "2026-01-15"})
    assert resp.status_code == 201
    assert resp.json()["amount"] == "12.50"
