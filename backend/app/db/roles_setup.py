"""Create per-role schemas, views and MySQL users. Run AFTER the seed:
    python -m app.db.roles_setup
(Re-run it whenever you re-run the seed, because the seed drops the base tables.)
"""
import pymysql

from app.config import ADMIN_PASSWORD, ADMIN_USER, DB_HOST, DB_NAME, DB_PORT
from app.roles import ROLES

B = DB_NAME
CUSTOMERS = (f"SELECT id, city, country, region, signup_date, "
             f"CONCAT(LEFT(email, 2), '***@', SUBSTRING_INDEX(email, '@', -1)) AS email_masked "
             f"FROM {B}.customers")
PRODUCTS = f"SELECT id, name, category, price FROM {B}.products"

SCHEMAS = {
    "viewer": {
        "orders_safe": f"SELECT id, order_date, status, region, total FROM {B}.orders",
        "products_safe": PRODUCTS,
    },
    "eu_manager": {
        "customers_safe": CUSTOMERS + " WHERE region = 'EU'",
        "orders_safe": (f"SELECT id, customer_id, order_date, status, region, total "
                        f"FROM {B}.orders WHERE region = 'EU'"),
        "order_items_safe": (f"SELECT oi.id, oi.order_id, oi.product_id, oi.quantity, oi.unit_price "
                             f"FROM {B}.order_items oi JOIN {B}.orders o ON o.id = oi.order_id "
                             f"WHERE o.region = 'EU'"),
        "products_safe": PRODUCTS,
    },
}


def main():
    conn = pymysql.connect(host=DB_HOST, port=DB_PORT, user=ADMIN_USER,
                           password=ADMIN_PASSWORD, autocommit=True)
    try:
        with conn.cursor() as cur:
            for key, views in SCHEMAS.items():
                role = ROLES[key]
                cur.execute(f"DROP DATABASE IF EXISTS {role.db}")
                cur.execute(f"CREATE DATABASE {role.db}")
                for name, select in views.items():
                    cur.execute(f"CREATE SQL SECURITY DEFINER VIEW {role.db}.{name} AS {select}")
                for host in ("localhost", "127.0.0.1"):
                    cur.execute("CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s "
                                "WITH MAX_USER_CONNECTIONS 5", (role.db_user, host, role.db_password))
                    cur.execute("ALTER USER %s@%s IDENTIFIED BY %s", (role.db_user, host, role.db_password))
                    for name in views:
                        cur.execute(f"GRANT SELECT ON {role.db}.{name} TO %s@%s", (role.db_user, host))
                print(f"{key}: schema {role.db}, user {role.db_user}, views {sorted(views)}")
            cur.execute("FLUSH PRIVILEGES")
    finally:
        conn.close()


if __name__ == "__main__":
    main()