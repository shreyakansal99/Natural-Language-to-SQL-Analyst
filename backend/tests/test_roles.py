import jwt
import pymysql
import pytest
from fastapi.testclient import TestClient

from app.config import DB_HOST, DB_PORT, DEMO_PASSWORD, JWT_SECRET
from app.executor import ExecutionError, run_query
from app.main import app
from app.roles import ROLES
from app.validator import ValidationError, validate

client = TestClient(app)
_tokens = {}


def headers(user):
    if user not in _tokens:
        r = client.post("/login", json={"username": user, "password": DEMO_PASSWORD})
        assert r.status_code == 200
        _tokens[user] = r.json()["token"]
    return {"Authorization": f"Bearer {_tokens[user]}"}


# --- validator
def test_viewer_cannot_query_customers_or_items():
    for t in ("customers_safe", "order_items_safe"):
        with pytest.raises(ValidationError):
            validate(f"SELECT * FROM {t}", ROLES["viewer"])


def test_analyst_can_query_customers():
    assert "LIMIT" in validate("SELECT * FROM customers_safe", ROLES["analyst"])


def test_cannot_use_another_roles_schema():
    with pytest.raises(ValidationError):
        validate("SELECT * FROM shop_analytics.orders_safe", ROLES["eu_manager"])


# --- the database itself (validator bypassed)
def test_viewer_has_no_customer_id_column():
    with pytest.raises(ExecutionError):
        run_query("SELECT customer_id FROM orders_safe", ROLES["viewer"])


def test_eu_manager_only_sees_eu():
    r = run_query("SELECT DISTINCT region FROM orders_safe", ROLES["eu_manager"])
    assert r["rows"] == [["EU"]]
    c = run_query("SELECT DISTINCT region FROM customers_safe", ROLES["eu_manager"])
    assert c["rows"] == [["EU"]]


def test_db_users_cannot_reach_other_roles_data():
    v = ROLES["viewer"]
    with pymysql.connect(host=DB_HOST, port=DB_PORT, user=v.db_user,
                         password=v.db_password, database=v.db) as c:
        for stmt in ("SELECT * FROM shop_analytics.orders_safe",
                     "SELECT * FROM shop_eu.orders_safe",
                     "SELECT * FROM shop.orders"):
            with pytest.raises(pymysql.MySQLError):
                c.cursor().execute(stmt)


# --- API
def test_no_token_is_rejected():
    assert client.post("/ask", json={"question": "hi"}).status_code == 401
    assert client.post("/run-sql", json={"sql": "SELECT 1"}).status_code == 401


def test_bad_login_is_rejected():
    assert client.post("/login", json={"username": "alex", "password": "wrong"}).status_code == 401


def test_viewer_cannot_use_run_sql():
    r = client.post("/run-sql", json={"sql": "SELECT COUNT(*) FROM orders_safe"},
                    headers=headers("vera"))
    assert r.status_code == 403


def test_forged_role_claim_is_ignored():
    forged = jwt.encode({"sub": "vera", "role": "analyst", "exp": 9999999999},
                        JWT_SECRET, algorithm="HS256")
    r = client.post("/run-sql", json={"sql": "SELECT COUNT(*) FROM orders_safe"},
                    headers={"Authorization": f"Bearer {forged}"})
    assert r.status_code == 403          # still a viewer: the role comes from the server


def test_token_signed_with_wrong_key_is_rejected():
    bad = jwt.encode({"sub": "alex", "exp": 9999999999}, "x" * 40, algorithm="HS256")
    r = client.post("/run-sql", json={"sql": "SELECT 1"}, headers={"Authorization": f"Bearer {bad}"})
    assert r.status_code == 401


def test_eu_manager_edit_sees_only_eu():
    r = client.post("/run-sql", json={"sql": "SELECT DISTINCT region FROM orders_safe"},
                    headers=headers("emma"))
    assert r.json()["rows"] == [["EU"]]