SCHEMA_DESCRIPTION = """
Database: MySQL. You may query ONLY these four views.

customers_safe (one row per customer)
  id INT, city TEXT, country TEXT, region TEXT ('NA','EU','APAC'),
  signup_date DATE, email_masked TEXT (already masked, e.g. 'jo***@example.com')

orders_safe (one row per order)
  id INT, customer_id INT -> customers_safe.id, order_date DATE,
  status TEXT ('completed','shipped','pending','cancelled','refunded'),
  region TEXT ('NA','EU','APAC'), total DECIMAL (order value; no currency is specified, so never assume one)
  "Order value" / "average order value" means orders_safe.total (one row per order). Never
  compute it from order_items_safe.

order_items_safe (one row per product line in an order)
  id INT, order_id INT -> orders_safe.id, product_id INT -> products_safe.id,
  quantity INT, unit_price DECIMAL

products_safe (one row per product)
  id INT, name TEXT, category TEXT ('Electronics','Home','Clothing','Sports','Books'),
  price DECIMAL (no currency specified)
  (line revenue = quantity * unit_price)

Data covers roughly the last 2 years of orders.
""".strip()


_range_cache: str | None = None


def data_range_note() -> str:
    """Look up the real order date range once (through the validated, read-only path)."""
    global _range_cache
    if _range_cache is None:
        try:
            from app.executor import run_query
            r = run_query("SELECT MIN(order_date), MAX(order_date) FROM orders_safe")
            lo, hi = r["rows"][0]
            _range_cache = f"Orders span {lo} to {hi}."
        except Exception:
            return "Orders cover roughly the last 2 years."
    return _range_cache