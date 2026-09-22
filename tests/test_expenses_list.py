def _seed(client):
    client.post("/expenses", json={"amount": 10, "category": "food", "date": "2026-01-01"})
    client.post("/expenses", json={"amount": 20, "category": "food", "date": "2026-01-15"})
    client.post("/expenses", json={"amount": 30, "category": "transport", "date": "2026-01-10"})


def test_list_filter_by_category(client):
    _seed(client)
    resp = client.get("/expenses", params={"category": "Food"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2
    assert all(item["category"] == "food" for item in body["items"])


def test_list_filter_by_date_range(client):
    _seed(client)
    resp = client.get("/expenses", params={"start_date": "2026-01-05", "end_date": "2026-01-31"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 2  # excludes the 2026-01-01 row


def test_list_filter_combined_category_and_date_range(client):
    _seed(client)
    resp = client.get("/expenses", params={"category": "food", "start_date": "2026-01-10"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["total"] == 1
    assert body["items"][0]["date"] == "2026-01-15"


def test_list_start_after_end_returns_400(client):
    resp = client.get("/expenses", params={"start_date": "2026-01-31", "end_date": "2026-01-01"})
    assert resp.status_code == 400
    assert resp.json()["error"]["code"] == "bad_request"


def test_list_empty_result(client):
    resp = client.get("/expenses", params={"category": "nonexistent"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["items"] == []
    assert body["total"] == 0


def test_list_sorted_date_desc_then_id_desc(client):
    client.post("/expenses", json={"amount": 1, "category": "food", "date": "2026-01-10"})
    client.post("/expenses", json={"amount": 2, "category": "food", "date": "2026-01-10"})
    client.post("/expenses", json={"amount": 3, "category": "food", "date": "2026-01-05"})
    resp = client.get("/expenses")
    dates_and_ids = [(item["date"], item["id"]) for item in resp.json()["items"]]
    assert dates_and_ids == [("2026-01-10", 2), ("2026-01-10", 1), ("2026-01-05", 3)]
