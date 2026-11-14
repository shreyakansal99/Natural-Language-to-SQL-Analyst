from dataclasses import dataclass

from app.config import (ANALYTICS_DB, NL_EU_PASSWORD, NL_READER_PASSWORD,
                        NL_VIEWER_PASSWORD)


@dataclass(frozen=True)
class Role:
    name: str
    db: str                  # MySQL schema holding this role's views
    db_user: str             # MySQL user this role connects as
    db_password: str
    tables: frozenset
    can_edit: bool
    scope_note: str = ""


ALL = frozenset({"customers_safe", "orders_safe", "order_items_safe", "products_safe"})

ROLES = {
    "viewer": Role("viewer", "shop_viewer", "nl_viewer", NL_VIEWER_PASSWORD,
                   frozenset({"orders_safe", "products_safe"}), can_edit=False),
    "analyst": Role("analyst", ANALYTICS_DB, "nl_reader", NL_READER_PASSWORD,
                    ALL, can_edit=True),
    "eu_manager": Role("eu_manager", "shop_eu", "nl_eu", NL_EU_PASSWORD, ALL, can_edit=True,
                       scope_note="This user only has access to EU data. All views are already limited to region 'EU'."),
}
DEFAULT_ROLE = ROLES["analyst"]

TABLE_DOCS = {
    "customers_safe": """customers_safe (one row per customer)
  id INT, city TEXT, country TEXT, region TEXT ('NA','EU','APAC'),
  signup_date DATE, email_masked TEXT (already masked)""",
    "orders_safe": """orders_safe (one row per order)
  id INT, customer_id INT -> customers_safe.id, order_date DATE,
  status TEXT ('completed','shipped','pending','cancelled','refunded'),
  region TEXT ('NA','EU','APAC'), total DECIMAL (order value; no currency is specified,
  so never assume one). "Order value" / "average order value" means orders_safe.total.""",
    "order_items_safe": """order_items_safe (one row per product line in an order)
  id INT, order_id INT -> orders_safe.id, product_id INT -> products_safe.id,
  quantity INT, unit_price DECIMAL (line revenue = quantity * unit_price)""",
    "products_safe": """products_safe (one row per product)
  id INT, name TEXT, category TEXT ('Electronics','Home','Clothing','Sports','Books'),
  price DECIMAL (no currency specified)""",
}
VIEWER_ORDERS_DOC = """orders_safe (one row per order)
  id INT, order_date DATE, status TEXT ('completed','shipped','pending','cancelled','refunded'),
  region TEXT ('NA','EU','APAC'), total DECIMAL (order value; no currency is specified).
  There is NO customer_id column for this user."""


def schema_for(role: Role) -> str:
    parts = ["Database: MySQL. You may query ONLY these views (this user has no others):", ""]
    for t in sorted(role.tables):
        parts.append(VIEWER_ORDERS_DOC if (role.name == "viewer" and t == "orders_safe")
                     else TABLE_DOCS[t])
        parts.append("")
    parts.append("If the question needs data that is not in these views, set cannot_answer_reason.")
    if role.scope_note:
        parts.append(role.scope_note)
    return "\n".join(parts)