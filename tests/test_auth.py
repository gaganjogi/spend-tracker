def test_missing_api_key_returns_401(unauthenticated_client):
    resp = unauthenticated_client.get("/expenses")
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


def test_wrong_api_key_returns_401(unauthenticated_client):
    resp = unauthenticated_client.get("/expenses", headers={"X-API-Key": "wrong-key"})
    assert resp.status_code == 401


def test_correct_api_key_succeeds(client):
    resp = client.get("/expenses")
    assert resp.status_code == 200


def test_post_expenses_requires_api_key(unauthenticated_client):
    resp = unauthenticated_client.post(
        "/expenses", json={"amount": 10, "category": "food", "date": "2026-01-01"}
    )
    assert resp.status_code == 401


def test_summary_requires_api_key(unauthenticated_client):
    resp = unauthenticated_client.get("/summary")
    assert resp.status_code == 401


def test_health_does_not_require_api_key(unauthenticated_client):
    resp = unauthenticated_client.get("/health")
    assert resp.status_code == 200
