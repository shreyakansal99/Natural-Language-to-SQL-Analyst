import pytest

from app.validator import ValidationError, validate

ATTACKS = [
    # stacked queries
    "SELECT * FROM orders_safe; DROP TABLE orders_safe;",
    "SELECT 1; /* hi */ DELETE FROM customers_safe",
    "sElEcT * fRoM orders_safe;dRoP/**/tAbLe orders_safe",
    # non-SELECT statements
    "DROP TABLE orders_safe",
    "DELETE FROM orders_safe",
    "UPDATE orders_safe SET total = 0",
    "INSERT INTO orders_safe (id) VALUES (1)",
    "SET GLOBAL read_only = 0",
    "CALL some_proc()",
    # file access / exfiltration
    "SELECT * FROM orders_safe INTO OUTFILE '/tmp/x'",
    "SELECT * FROM orders_safe INTO DUMPFILE '/tmp/x'",
    "SELECT LOAD_FILE('/etc/passwd')",
    # resource exhaustion and locks
    "SELECT SLEEP(10)",
    "SELECT BENCHMARK(100000000, MD5('a'))",
    "SELECT GET_LOCK('a', 10)",
    "SELECT * FROM orders_safe FOR UPDATE",
    "SELECT * FROM orders_safe LOCK IN SHARE MODE",
    # executable comments
    "SELECT /*! SLEEP(5) */ 1",
    "SELECT 1 /*!50000 UNION SELECT password_hash FROM users_credentials */",
    # variables and info disclosure
    "SELECT @@version",
    "SELECT @a := 1",
    "SELECT VERSION()",
    "SELECT USER()",
    "SELECT CURRENT_USER()",
    "SELECT DATABASE()",
    # tables outside the allowlist
    "SELECT * FROM customers",
    "SELECT * FROM users_credentials",
    "SELECT * FROM shop.customers",
    "SELECT * FROM shop.users_credentials",
    "SELECT * FROM information_schema.tables",
    "SELECT * FROM mysql.user",
    "SELECT * FROM performance_schema.threads",
    # smuggling a forbidden table inside other constructs
    "WITH x AS (SELECT * FROM users_credentials) SELECT * FROM x",
    "SELECT (SELECT password_hash FROM users_credentials LIMIT 1)",
    "SELECT * FROM orders_safe WHERE id = 1 UNION SELECT * FROM users_credentials",
    # garbage and limits
    "",
    "   ",
    "SELECT * FROM",
    "SELECT * FROM orders_safe WHERE id = 1 " + "OR id = 2 " * 400,
    "SELECT * FROM orders_safe a JOIN orders_safe b JOIN orders_safe c "
    "JOIN orders_safe d JOIN orders_safe e JOIN orders_safe f JOIN orders_safe g",
]


@pytest.mark.parametrize("sql", ATTACKS)
def test_attack_blocked(sql):
    with pytest.raises(ValidationError):
        validate(sql)


LEGIT = [
    "SELECT COUNT(*) FROM orders_safe",
    "SELECT region, SUM(total) AS revenue FROM orders_safe "
    "GROUP BY region ORDER BY revenue DESC",
    "SELECT c.country, COUNT(*) AS n FROM customers_safe c "
    "JOIN orders_safe o ON o.customer_id = c.id GROUP BY c.country",
    "SELECT YEAR(order_date) AS y, MONTH(order_date) AS m, SUM(total) AS revenue "
    "FROM orders_safe GROUP BY y, m ORDER BY y, m",
    "WITH t AS (SELECT region, SUM(total) AS s FROM orders_safe GROUP BY region) "
    "SELECT * FROM t",
    "SELECT * FROM shop_analytics.products_safe",
    "SELECT category, ROUND(AVG(price), 2) FROM products_safe GROUP BY category",
]


@pytest.mark.parametrize("sql", LEGIT)
def test_legit_passes_and_is_limited(sql):
    out = validate(sql)
    assert "LIMIT" in out.upper()
    assert ";" not in out


def test_limit_is_capped():
    assert "LIMIT 500" in validate("SELECT * FROM orders_safe LIMIT 999999")


def test_small_limit_is_kept():
    assert "LIMIT 10" in validate("SELECT * FROM orders_safe LIMIT 10")


def test_semicolon_then_comment_is_rejected():
    # Strict rule: a second statement-like fragment is refused, even a comment.
    with pytest.raises(ValidationError):
        validate("SELECT * FROM orders_safe; -- ; DROP TABLE orders_safe")


def test_single_trailing_semicolon_is_fine():
    out = validate("SELECT * FROM orders_safe;")
    assert ";" not in out
    assert "LIMIT" in out.upper()


def test_comments_are_stripped_from_output():
    out = validate("SELECT * FROM orders_safe -- DROP TABLE orders_safe")
    assert "DROP" not in out.upper()


def test_and_or_not_are_allowed():
    out = validate("SELECT * FROM orders_safe WHERE total > 10 AND NOT status = 'x' OR id = 1")
    assert "LIMIT" in out.upper()