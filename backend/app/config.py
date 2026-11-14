import os
from dotenv import load_dotenv

load_dotenv()


def _required(name: str) -> str:
    value = os.getenv(name)
    if not value:
        raise RuntimeError(f"{name} is not set in .env")
    return value


MISTRAL_API_KEY = _required("MISTRAL_API_KEY")
MISTRAL_MODEL = os.getenv("MISTRAL_MODEL", "mistral-large-latest")

DB_HOST = os.getenv("DB_HOST", "127.0.0.1")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_NAME = os.getenv("DB_NAME", "shop")
ANALYTICS_DB = os.getenv("ANALYTICS_DB", "shop_analytics")

ADMIN_USER = os.getenv("ADMIN_USER", "root")
ADMIN_PASSWORD = _required("ADMIN_PASSWORD")
NL_READER_PASSWORD = _required("NL_READER_PASSWORD")

MAX_ROWS = int(os.getenv("MAX_ROWS", "500"))
STATEMENT_TIMEOUT_MS = int(os.getenv("STATEMENT_TIMEOUT_MS", "5000"))

JWT_SECRET = _required("JWT_SECRET")
DEMO_PASSWORD = _required("DEMO_PASSWORD")
NL_VIEWER_PASSWORD = _required("NL_VIEWER_PASSWORD")
NL_EU_PASSWORD = _required("NL_EU_PASSWORD")