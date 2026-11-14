"""Run validated SQL as the locked-down nl_reader user.

Layers here: validator (always called), read-only session, server-side
timeout, client-side socket timeout, row cap, no multi-statement support,
safe error messages. nl_reader's privileges are the final backstop.
"""
import datetime
import decimal
import logging
import time

import pymysql

from app.config import DB_HOST, DB_PORT, MAX_ROWS, STATEMENT_TIMEOUT_MS
from app.roles import DEFAULT_ROLE
from app.validator import validate

log = logging.getLogger("executor")


class ExecutionError(Exception):
    """Query failed at run time. The message is safe to show to the user."""


def _connect(role, timeout_ms: int):
    return pymysql.connect(
        host=DB_HOST, port=DB_PORT,
        user=role.db_user, password=role.db_password, database=role.db,
        autocommit=True,
        connect_timeout=5,
        read_timeout=timeout_ms // 1000 + 2,
        write_timeout=5,
        init_command=("SET SESSION transaction_read_only=1, "
                      f"SESSION max_execution_time={int(timeout_ms)}"),
    )


def _jsonable(value):
    if isinstance(value, decimal.Decimal):
        return float(value)
    if isinstance(value, (datetime.date, datetime.datetime, datetime.time)):
        return value.isoformat()
    if isinstance(value, datetime.timedelta):
        return str(value)
    if isinstance(value, (bytes, bytearray)):
        return "<binary>"
    return value


def _execute(safe_sql: str, timeout_ms: int, role=None) -> dict:
    role = role or DEFAULT_ROLE
    started = time.monotonic()
    conn = None
    try:
        conn = _connect(role, timeout_ms)
        with conn.cursor() as cur:
            cur.execute(safe_sql)
            columns = [d[0] for d in cur.description] if cur.description else []
            fetched = cur.fetchmany(MAX_ROWS + 1)
    except pymysql.err.OperationalError as e:
        code = e.args[0] if e.args else None
        log.warning("operational error %s", code)
        if code in (3024, 2013, 2006):      # timeout / lost connection
            raise ExecutionError("The query took too long. Try narrowing it "
                                 "(a date range, a filter, fewer groups).")
        raise ExecutionError("The database could not run this query.")
    except pymysql.MySQLError as e:
        code = e.args[0] if e.args else None
        log.warning("database error %s", code)
        # Never leak raw MySQL messages (they can expose schema details)
        raise ExecutionError("The query was rejected by the database.")
    finally:
        if conn is not None:
            conn.close()

    truncated = len(fetched) > MAX_ROWS
    rows = [[_jsonable(v) for v in row] for row in fetched[:MAX_ROWS]]
    return {
        "sql": safe_sql,
        "columns": columns,
        "rows": rows,
        "row_count": len(rows),
        "truncated": truncated,
        "elapsed_ms": int((time.monotonic() - started) * 1000),
    }


def run_query(sql: str, role=None) -> dict:
    role = role or DEFAULT_ROLE
    safe_sql = validate(sql, role)
    return _execute(safe_sql, STATEMENT_TIMEOUT_MS, role)