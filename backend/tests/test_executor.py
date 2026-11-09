import time

import pytest

from app.executor import ExecutionError, _execute, run_query
from app.validator import ValidationError


def test_basic_query_returns_rows():
    r = run_query("SELECT region, COUNT(*) AS n FROM orders_safe GROUP BY region")
    assert r["columns"] == ["region", "n"]
    assert r["row_count"] == 3
    assert r["truncated"] is False


def test_values_are_json_friendly():
    r = run_query("SELECT order_date, total FROM orders_safe LIMIT 1")
    assert isinstance(r["rows"][0][0], str)      # date -> ISO string
    assert isinstance(r["rows"][0][1], float)    # Decimal -> float


def test_row_cap_applies():
    r = run_query("SELECT * FROM order_items_safe")   # thousands of rows
    assert r["row_count"] == 500
    assert "LIMIT 500" in r["sql"]


def test_emails_are_masked_in_results():
    r = run_query("SELECT email_masked FROM customers_safe LIMIT 5")
    assert all("***@" in row[0] for row in r["rows"])


@pytest.mark.parametrize("bad", [
    "DROP TABLE orders_safe",
    "SELECT * FROM users_credentials",
    "SELECT SLEEP(5)",
    "SELECT * FROM orders_safe; DELETE FROM orders_safe",
])
def test_run_query_rejects_bad_sql_before_the_database(bad):
    with pytest.raises(ValidationError):
        run_query(bad)


def test_database_layers_still_hold_if_validator_is_bypassed():
    # Call the internal function directly: the DB itself must refuse.
    with pytest.raises(ExecutionError):
        _execute("DROP TABLE orders_safe", 5000)
    with pytest.raises(ExecutionError):
        _execute("SELECT * FROM shop.users_credentials", 5000)


def test_timeout_stops_a_slow_query():
    # SLEEP is blocked by the validator, but the DB-level timeout must also
    # work on its own.
    started = time.monotonic()
    try:
        _execute("SELECT SLEEP(8)", 1000)
    except ExecutionError:
        pass
    assert time.monotonic() - started < 6