"""Validate LLM-generated SQL before it goes anywhere near the database.

Rules: exactly one SELECT, only the allowlisted views, only allowlisted
functions, no variables/locks/INTO, forced LIMIT. The caller must execute the
RETURNED string (regenerated from the AST), never the original text.
"""
import sqlglot
from sqlglot import exp
from sqlglot.errors import SqlglotError

from app.config import ANALYTICS_DB, MAX_ROWS

MAX_SQL_CHARS = 2000
MAX_JOINS = 5

ALLOWED_TABLES = {"customers_safe", "orders_safe", "order_items_safe", "products_safe"}

# Function names as sqlglot reports them (uppercase). Anything not listed is
# rejected, which is what blocks SLEEP, BENCHMARK, LOAD_FILE, GET_LOCK, USER...
# If a legitimate function is rejected, the error shows its name: add it here.
ALLOWED_FUNCS = {
    # aggregates
    "COUNT", "SUM", "AVG", "MIN", "MAX",
    # math
    "ROUND", "ABS", "CEIL", "FLOOR",
    # null / conditional
    "COALESCE", "NULLIF", "IF", "CASE",
    # text
    "LOWER", "UPPER", "LENGTH", "TRIM", "CONCAT", "SUBSTRING",
    # casting / dates
    "CAST", "EXTRACT", "YEAR", "MONTH", "DAY", "QUARTER", "WEEK",
    "DATE_ADD", "DATE_SUB", "DATEDIFF", "DATE_DIFF", "DATE_TRUNC",
    "CURRENT_DATE", "TS_OR_DS_TO_DATE", "TIME_TO_STR",
    # window functions
    "ROW_NUMBER", "RANK", "DENSE_RANK", "LAG", "LEAD",
}

_FORBIDDEN_NAMES = [
    "Insert", "Update", "Delete", "Drop", "Create", "Alter", "Command", "Merge",
    "Into",                       # SELECT ... INTO OUTFILE / @var
    "Lock",                       # FOR UPDATE / LOCK IN SHARE MODE
    "Set", "Use", "Transaction", "Commit", "Rollback", "Kill",
    "Parameter", "SessionParameter", "Placeholder",   # @a, @@version, ?
]
FORBIDDEN_NODES = tuple(getattr(exp, n) for n in _FORBIDDEN_NAMES if hasattr(exp, n))


class ValidationError(Exception):
    """The SQL was rejected. The message is safe to show to the user."""


def _function_name(node: exp.Expression) -> str:
    if isinstance(node, exp.Anonymous):
        return str(node.name).upper()
    return node.sql_name().upper()


def validate(sql: str) -> str:
    if not isinstance(sql, str) or not sql.strip():
        raise ValidationError("Empty query")
    if len(sql) > MAX_SQL_CHARS:
        raise ValidationError("Query too long")
    if "\x00" in sql:
        raise ValidationError("Invalid characters")
    # MySQL EXECUTES /*! ... */ (and /*M! ... */) contents; most parsers treat
    # them as comments. Refuse them outright instead of arguing about parsing.
    if "/*!" in sql or "/*M!" in sql:
        raise ValidationError("Executable comments are not allowed")

    # 1. Parse into an AST; exactly one statement
    try:
        statements = [s for s in sqlglot.parse(sql, read="mysql") if s is not None]
    except SqlglotError:
        raise ValidationError("Could not parse the SQL")
    if len(statements) != 1:
        raise ValidationError("Exactly one statement is allowed")
    tree = statements[0]

    # 2. Must be a plain SELECT (WITH ... SELECT is still a Select node)
    if not isinstance(tree, exp.Select):
        raise ValidationError("Only SELECT queries are allowed")

    # 3. Forbidden constructs anywhere in the tree (subqueries, CTEs, ...)
    for node in tree.walk():
        if isinstance(node, FORBIDDEN_NODES):
            raise ValidationError("This query uses a forbidden construct")

    # 4. Table allowlist: only the safe views, only in the analytics database
    cte_names = {c.alias_or_name.lower() for c in tree.find_all(exp.CTE)}
    for table in tree.find_all(exp.Table):
        if not isinstance(table.this, exp.Identifier):
            raise ValidationError("Table functions are not allowed")
        if table.args.get("catalog"):
            raise ValidationError("Table not allowed")
        name = table.name.lower()
        db = table.db.lower() if table.db else ""
        if db:
            if db != ANALYTICS_DB.lower() or name not in ALLOWED_TABLES:
                raise ValidationError(f"Table not allowed: {db}.{name}")
        elif name not in ALLOWED_TABLES and name not in cte_names:
            raise ValidationError(f"Table not allowed: {name}")

    # 5. Function allowlist
    for node in tree.find_all(exp.Func):
        if isinstance(node, (exp.Binary, exp.Unary)):   # AND, OR, NOT, +, -, =, ...
            continue
        fname = _function_name(node)
        if fname not in ALLOWED_FUNCS:
            raise ValidationError(f"Function not allowed: {fname}")

    # 6. Complexity limit (blocks huge join explosions)
    if len(list(tree.find_all(exp.Join))) > MAX_JOINS:
        raise ValidationError("Too many joins")

    # 7. Force a row cap
    limit = tree.args.get("limit")
    expr = limit.expression if limit is not None else None
    within_cap = (isinstance(expr, exp.Literal) and expr.is_int
                  and int(expr.name) <= MAX_ROWS)
    if not within_cap:
        tree = tree.limit(MAX_ROWS, copy=False)

    # 8. Execute THIS string, never the original: comments and trailing
    #    fragments are gone, so what was validated is exactly what runs.
    return tree.sql(dialect="mysql", comments=False)