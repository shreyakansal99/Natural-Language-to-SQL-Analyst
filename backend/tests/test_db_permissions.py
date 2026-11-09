import pymysql
import pytest

from app.config import (ANALYTICS_DB, DB_HOST, DB_NAME, DB_PORT,
                        NL_READER_PASSWORD, STATEMENT_TIMEOUT_MS)


@pytest.fixture
def conn():
    c = pymysql.connect(
        host=DB_HOST, port=DB_PORT, user="nl_reader",
        password=NL_READER_PASSWORD, database=ANALYTICS_DB, autocommit=True,
        init_command=("SET SESSION transaction_read_only=1, "
                      f"SESSION max_execution_time={STATEMENT_TIMEOUT_MS}"),
    )
    yield c
    c.close()


def run(conn, stmt):
    with conn.cursor() as cur:
        cur.execute(stmt)
        return cur.fetchall()


@pytest.mark.parametrize("stmt", [
    f"DROP TABLE {DB_NAME}.customers",
    "DROP VIEW customers_safe",
    "DELETE FROM customers_safe",
    "UPDATE orders_safe SET total = 0",
    "INSERT INTO orders_safe (id) VALUES (999999)",
    "CREATE TABLE evil (a INT)",
    f"TRUNCATE TABLE {DB_NAME}.orders",
    f"SELECT * FROM {DB_NAME}.customers",
    f"SELECT * FROM {DB_NAME}.users_credentials",
    "GRANT ALL PRIVILEGES ON *.* TO 'nl_reader'@'localhost'",
    f"SELECT 1; DROP TABLE {DB_NAME}.customers",     # stacked query
    "SELECT * INTO OUTFILE '/tmp/leak.txt' FROM customers_safe",
])
def test_database_blocks(conn, stmt):
    with pytest.raises(pymysql.MySQLError):
        run(conn, stmt)


def test_base_tables_are_invisible(conn):
    rows = run(conn, "SELECT COUNT(*) FROM information_schema.tables "
                     f"WHERE table_schema = '{DB_NAME}'")
    assert rows[0][0] == 0


def test_email_is_masked(conn):
    email = run(conn, "SELECT email_masked FROM customers_safe LIMIT 1")[0][0]
    assert "***@" in email


def test_safe_views_return_data(conn):
    assert run(conn, "SELECT COUNT(*) FROM orders_safe")[0][0] > 0  