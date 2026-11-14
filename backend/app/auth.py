"""Demo authentication. In production use SSO (Okta, Azure AD) and a real user store.
The role is ALWAYS looked up server-side; the token only carries the username."""
import hashlib
import hmac
import os
import time
from collections import defaultdict, deque
from dataclasses import dataclass

import jwt
from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from app.config import DEMO_PASSWORD, JWT_SECRET
from app.roles import ROLES, Role


def _hash(password: str, salt: bytes) -> bytes:
    return hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 200_000)


_DEMO = {"vera": "viewer", "alex": "analyst", "emma": "eu_manager"}
USERS = {}
for _name, _role in _DEMO.items():
    _salt = os.urandom(16)
    USERS[_name] = {"role": _role, "salt": _salt, "hash": _hash(DEMO_PASSWORD, _salt)}
_DUMMY_SALT = os.urandom(16)


def authenticate(username: str, password: str) -> bool:
    user = USERS.get(username.lower())
    salt = user["salt"] if user else _DUMMY_SALT          # same work either way
    digest = _hash(password, salt)
    return bool(user) and hmac.compare_digest(digest, user["hash"])


def make_token(username: str) -> str:
    return jwt.encode({"sub": username.lower(), "exp": int(time.time()) + 8 * 3600},
                      JWT_SECRET, algorithm="HS256")


@dataclass
class CurrentUser:
    username: str
    role: Role


_bearer = HTTPBearer(auto_error=False)


def current_user(creds: HTTPAuthorizationCredentials = Depends(_bearer)) -> CurrentUser:
    if creds is None:
        raise HTTPException(401, "Please log in.")
    try:
        claims = jwt.decode(creds.credentials, JWT_SECRET, algorithms=["HS256"])
    except jwt.PyJWTError:
        raise HTTPException(401, "Your session is invalid or has expired. Please log in again.")
    user = USERS.get(claims.get("sub", ""))
    if not user:
        raise HTTPException(401, "Unknown user.")
    return CurrentUser(claims["sub"], ROLES[user["role"]])      # role from the server, not the token


# ---- simple in-memory rate limiter (single process; use Redis in production)
_hits = defaultdict(deque)


def rate_limit(key: str, limit: int, window: int = 60) -> None:
    now = time.monotonic()
    q = _hits[key]
    while q and now - q[0] > window:
        q.popleft()
    if len(q) >= limit:
        raise HTTPException(429, "Too many requests. Please wait a minute and try again.")
    q.append(now)