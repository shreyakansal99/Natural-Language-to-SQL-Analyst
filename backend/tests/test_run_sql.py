import pytest
from fastapi.testclient import TestClient

from app.config import DEMO_PASSWORD
from app.main import app

client = TestClient(app)
_token = {}


def headers():
    if "t" not in _token:
        r = client.post("/login", json={"username": "alex", "password": DEMO_PASSWORD})
        assert r.status_code == 200
        _token["t"] = r.json()["token"]
    return {"Authorization": f"Bearer {_token['t']}"}


def post(sql):
    return client.post("/run-sql", json={"sql": sql}, headers=headers())


def test_valid_edit_runs():
    body = post("SELECT region, COUNT(*) AS n FROM orders_safe GROUP BY region").json()
    assert body["status"] == "ok" and body["row_count"] == 3


@pytest.mark.parametrize("sql", [
    "DROP TABLE orders_safe",
    "SELECT * FROM orders_safe; DELETE FROM orders_safe",
    "SELECT * FROM users_credentials",
    "SELECT * FROM shop.customers",
    "SELECT SLEEP(10)",
    "SELECT /*! SLEEP(5) */ 1",
    "SELECT * FROM orders_safe INTO OUTFILE '/tmp/x'",
    "SELECT password_hash FROM users_credentials",
    "SELECT * FROM information_schema.tables",
    "UPDATE orders_safe SET total = 0",
])


def test_attacks_through_the_edit_endpoint_are_rejected(sql):
    body = post(sql).json()
    assert body["status"] in ("rejected", "error")
    assert "rows" not in body


def test_row_cap_applies_to_edits():
    body = post("SELECT * FROM order_items_safe LIMIT 100000").json()
    assert body["status"] == "ok" and body["row_count"] == 500


def test_oversized_sql_is_refused_by_the_api():
    assert post("SELECT 1 " + "x" * 3000).status_code == 422


def test_error_messages_do_not_leak_mysql_details():
    body = post("SELECT nonexistent_col FROM orders_safe").json()
    assert body["status"] == "error"
    assert "nonexistent_col" not in body["message"]