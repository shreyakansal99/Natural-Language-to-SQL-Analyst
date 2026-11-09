"""Seed MySQL with FAKE data, the nl_reader user, and safe views.

Run from backend/:  python -m app.db.seed
WARNING: drops and recreates the DB_NAME and ANALYTICS_DB databases.
"""
import hashlib
import random
from datetime import date, timedelta

import pymysql
from faker import Faker

from app.config import (ADMIN_PASSWORD, ADMIN_USER, ANALYTICS_DB, DB_HOST,
                        DB_NAME, DB_PORT, NL_READER_PASSWORD)

N_CUSTOMERS, N_ORDERS = 500, 3000
random.seed(42)
Faker.seed(42)
fake = Faker()

REGIONS = {
    "NA": [("United States", ["New York", "Chicago", "Austin", "Seattle"]),
           ("Canada", ["Toronto", "Vancouver"])],
    "EU": [("Germany", ["Berlin", "Munich"]), ("France", ["Paris", "Lyon"]),
           ("Spain", ["Madrid", "Barcelona"])],
    "APAC": [("India", ["Delhi", "Mumbai", "Bengaluru"]),
             ("Japan", ["Tokyo", "Osaka"]), ("Australia", ["Sydney", "Melbourne"])],
}
CATEGORIES = {
    "Electronics": ["Headphones", "Speaker", "Charger", "Keyboard"],
    "Home": ["Lamp", "Blender", "Cushion", "Kettle"],
    "Clothing": ["Jacket", "T-Shirt", "Sneakers", "Cap"],
    "Sports": ["Yoga Mat", "Dumbbell", "Water Bottle", "Backpack"],
    "Books": ["Novel", "Cookbook", "Atlas", "Journal"],
}

# PyMySQL runs one statement per execute(), so these are lists.
TABLE_STATEMENTS = [
    """CREATE TABLE customers (
         id INT PRIMARY KEY,
         full_name VARCHAR(100) NOT NULL,
         email VARCHAR(150) NOT NULL,
         phone VARCHAR(60),
         address VARCHAR(255),
         date_of_birth DATE,
         city VARCHAR(60) NOT NULL,
         country VARCHAR(60) NOT NULL,
         region VARCHAR(10) NOT NULL,
         signup_date DATE NOT NULL
       )""",
    # Sensitive: nl_reader gets NO access to this table, ever.
    """CREATE TABLE users_credentials (
         customer_id INT PRIMARY KEY,
         password_hash VARCHAR(100) NOT NULL,
         FOREIGN KEY (customer_id) REFERENCES customers(id)
       )""",
    """CREATE TABLE products (
         id INT PRIMARY KEY,
         name VARCHAR(100) NOT NULL,
         category VARCHAR(50) NOT NULL,
         price DECIMAL(10,2) NOT NULL
       )""",
    """CREATE TABLE orders (
         id INT PRIMARY KEY,
         customer_id INT NOT NULL,
         order_date DATE NOT NULL,
         status VARCHAR(20) NOT NULL,
         region VARCHAR(10) NOT NULL,
         total DECIMAL(12,2) NOT NULL,
         FOREIGN KEY (customer_id) REFERENCES customers(id),
         INDEX (order_date)
       )""",
    """CREATE TABLE order_items (
         id INT PRIMARY KEY,
         order_id INT NOT NULL,
         product_id INT NOT NULL,
         quantity INT NOT NULL,
         unit_price DECIMAL(10,2) NOT NULL,
         FOREIGN KEY (order_id) REFERENCES orders(id),
         FOREIGN KEY (product_id) REFERENCES products(id)
       )""",
]

# Views run with the DEFINER's privileges, so nl_reader can read a view
# without having any access to the base tables behind it.
VIEWS = {
    "customers_safe": f"""
        SELECT id, city, country, region, signup_date,
               CONCAT(LEFT(email, 2), '***@', SUBSTRING_INDEX(email, '@', -1)) AS email_masked
        FROM {DB_NAME}.customers""",
    "orders_safe": f"""
        SELECT id, customer_id, order_date, status, region, total
        FROM {DB_NAME}.orders""",
    "order_items_safe": f"""
        SELECT id, order_id, product_id, quantity, unit_price
        FROM {DB_NAME}.order_items""",
    "products_safe": f"""
        SELECT id, name, category, price
        FROM {DB_NAME}.products""",
}

READER_HOSTS = ["localhost", "127.0.0.1"]


def insert(cur, table, rows):
    placeholders = ",".join(["%s"] * len(rows[0]))
    cur.executemany(f"INSERT INTO {table} VALUES ({placeholders})", rows)


def build_data():
    today = date.today()

    customers = []
    for cid in range(1, N_CUSTOMERS + 1):
        region = random.choice(list(REGIONS))
        country, cities = random.choice(REGIONS[region])
        customers.append((
            cid, fake.name(), fake.email(), fake.phone_number(),
            fake.address().replace("\n", ", "),
            fake.date_of_birth(minimum_age=18, maximum_age=80),
            random.choice(cities), country, region,
            fake.date_between(start_date="-3y", end_date="-1y"),
        ))

    creds = [(c[0], hashlib.sha256(fake.password().encode()).hexdigest())
             for c in customers]  # fake hashes

    products, pid = [], 1
    for category, names in CATEGORIES.items():
        for name in names:
            label = f"{random.choice(['Classic', 'Pro', 'Mini', 'Eco'])} {name}"
            products.append((pid, label, category, round(random.uniform(8, 250), 2)))
            pid += 1

    orders, items, item_id = [], [], 1
    for oid in range(1, N_ORDERS + 1):
        cust = random.choice(customers)
        status = random.choices(
            ["completed", "shipped", "pending", "cancelled", "refunded"],
            weights=[60, 15, 10, 10, 5])[0]
        total = 0.0
        for _ in range(random.randint(1, 4)):
            prod = random.choice(products)
            qty = random.randint(1, 3)
            items.append((item_id, oid, prod[0], qty, prod[3]))
            item_id += 1
            total += prod[3] * qty
        orders.append((oid, cust[0], today - timedelta(days=random.randint(0, 730)),
                       status, cust[8], round(total, 2)))
    return customers, creds, products, orders, items


def main():
    customers, creds, products, orders, items = build_data()

    conn = pymysql.connect(host=DB_HOST, port=DB_PORT, user=ADMIN_USER,
                           password=ADMIN_PASSWORD, autocommit=True)
    try:
        with conn.cursor() as cur:
            # 1. Fresh databases
            for db in (DB_NAME, ANALYTICS_DB):
                cur.execute(f"DROP DATABASE IF EXISTS {db}")
                cur.execute(f"CREATE DATABASE {db}")
            cur.execute(f"USE {DB_NAME}")

            # 2. Tables + fake data
            for stmt in TABLE_STATEMENTS:
                cur.execute(stmt)
            insert(cur, "customers", customers)
            insert(cur, "users_credentials", creds)
            insert(cur, "products", products)
            insert(cur, "orders", orders)
            insert(cur, "order_items", items)

            # 3. Safe views in the analytics database
            for name, select in VIEWS.items():
                cur.execute(f"CREATE SQL SECURITY DEFINER VIEW {ANALYTICS_DB}.{name} AS {select}")

            # 4. The locked-down user: SELECT on the four views, nothing else
            for host in READER_HOSTS:
                cur.execute("CREATE USER IF NOT EXISTS %s@%s IDENTIFIED BY %s "
                            "WITH MAX_USER_CONNECTIONS 5",
                            ("nl_reader", host, NL_READER_PASSWORD))
                cur.execute("ALTER USER %s@%s IDENTIFIED BY %s",
                            ("nl_reader", host, NL_READER_PASSWORD))
                for name in VIEWS:
                    cur.execute(f"GRANT SELECT ON {ANALYTICS_DB}.{name} TO %s@%s",
                                ("nl_reader", host))
            cur.execute("FLUSH PRIVILEGES")
    finally:
        conn.close()

    print(f"Seeded {len(customers)} customers, {len(products)} products, "
          f"{len(orders)} orders, {len(items)} order items.")
    print(f"User nl_reader ready: SELECT only on {ANALYTICS_DB}.* views.")


if __name__ == "__main__":
    main()