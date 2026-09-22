def test_summary_totals_by_category(client):
    client.post("/expenses", json={"amount": 10, "category": "food", "date": "2026-01-05"})
    client.post("/expenses", json={"amount": 20, "category": "transport", "date": "2026-01-05"})
    resp = client.get("/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == "30.00"
    by_cat = {c["category"]: c["amount"] for c in body["by_category"]}
    assert by_cat == {"food": "10.00", "transport": "20.00"}


def test_summary_month_over_month_math(client):
    client.post("/expenses", json={"amount": 100, "category": "food", "date": "2026-01-05"})
    client.post("/expenses", json={"amount": 150, "category": "food", "date": "2026-02-05"})
    resp = client.get("/summary", params={"month": "2026-02"})
    mom = resp.json()["month_over_month"]
    assert mom["previous_total"] == "100.00"
    assert mom["current_total"] == "150.00"
    assert mom["change_amount"] == "50.00"
    assert mom["change_percent"] == "50.00"


def test_summary_previous_month_zero_gives_null_percent(client):
    client.post("/expenses", json={"amount": 100, "category": "food", "date": "2026-02-05"})
    resp = client.get("/summary", params={"month": "2026-02"})
    mom = resp.json()["month_over_month"]
    assert mom["previous_total"] == "0.00"
    assert mom["change_percent"] is None


def test_summary_january_compares_to_previous_december(client):
    client.post("/expenses", json={"amount": 100, "category": "food", "date": "2025-12-10"})
    client.post("/expenses", json={"amount": 120, "category": "food", "date": "2026-01-10"})
    resp = client.get("/summary", params={"month": "2026-01"})
    mom = resp.json()["month_over_month"]
    assert mom["previous_month"] == "2025-12"
    assert mom["previous_total"] == "100.00"
    assert mom["current_total"] == "120.00"


def test_summary_rising_category_triggers_above_20_percent(client):
    client.post("/expenses", json={"amount": 100, "category": "food", "date": "2026-01-05"})
    client.post("/expenses", json={"amount": 121, "category": "food", "date": "2026-02-05"})
    resp = client.get("/summary", params={"month": "2026-02"})
    flags = {r["category"]: r for r in resp.json()["rising_categories"]}
    assert "food" in flags
    assert flags["food"]["flag"] == "increase"


def test_summary_exactly_20_percent_does_not_trigger(client):
    client.post("/expenses", json={"amount": 100, "category": "food", "date": "2026-01-05"})
    client.post("/expenses", json={"amount": 120, "category": "food", "date": "2026-02-05"})
    resp = client.get("/summary", params={"month": "2026-02"})
    flagged = {r["category"] for r in resp.json()["rising_categories"]}
    assert "food" not in flagged


def test_summary_new_category_is_flagged_new_not_increase(client):
    client.post("/expenses", json={"amount": 30, "category": "rent", "date": "2026-02-05"})
    resp = client.get("/summary", params={"month": "2026-02"})
    flags = {r["category"]: r for r in resp.json()["rising_categories"]}
    assert flags["rent"]["flag"] == "new"
    assert flags["rent"]["change_percent"] is None


def test_summary_bad_month_format_returns_400(client):
    resp = client.get("/summary", params={"month": "not-a-month"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "bad_request"


def test_summary_start_after_end_returns_400(client):
    resp = client.get("/summary", params={"start_date": "2026-01-31", "end_date": "2026-01-01"})
    assert resp.status_code == 400


def test_summary_empty_db_returns_zeros(client):
    resp = client.get("/summary")
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == "0.00"
    assert body["by_category"] == []
    assert body["month_over_month"]["change_percent"] is None
    assert body["rising_categories"] == []
