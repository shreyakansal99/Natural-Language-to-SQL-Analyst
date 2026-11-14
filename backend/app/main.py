import time

from fastapi import Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.auth import (USERS, CurrentUser, authenticate, current_user,
                      make_token, rate_limit)
from app.executor import ExecutionError, run_query
from app.pipeline import answer, audit_edit
from app.roles import ROLES
from app.validator import ValidationError

app = FastAPI(title="Query-to-SQL Analyst")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type", "Authorization"],
)


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=100)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class RunSqlRequest(BaseModel):
    sql: str = Field(min_length=1, max_length=2000)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/login")
def login(req: LoginRequest):
    rate_limit(f"login:{req.username.lower()}", 5)
    if not authenticate(req.username, req.password):
        raise HTTPException(401, "Invalid username or password.")
    name = req.username.lower()
    role = ROLES[USERS[name]["role"]]
    return {"token": make_token(name), "username": name,
            "role": role.name, "can_edit": role.can_edit}


@app.post("/ask")
def ask(req: AskRequest, user: CurrentUser = Depends(current_user)):
    rate_limit(f"ask:{user.username}", 10)
    return answer(req.question, user.role, user.username)


@app.post("/run-sql")
def run_sql(req: RunSqlRequest, user: CurrentUser = Depends(current_user)):
    started = time.monotonic()
    ms = lambda: int((time.monotonic() - started) * 1000)
    who = dict(user=user.username, role=user.role.name)
    if not user.role.can_edit:
        audit_edit(req.sql, "denied", 0, ms(), rule="role", **who)
        raise HTTPException(403, "Your role cannot run edited SQL.")
    rate_limit(f"sql:{user.username}", 60)
    try:
        res = run_query(req.sql, user.role)
    except ValidationError as e:
        audit_edit(req.sql, "rejected", 0, ms(), rule="validator", **who)
        return {"status": "rejected", "message": str(e)}
    except ExecutionError as e:
        audit_edit(req.sql, "error", 0, ms(), rule="executor", **who)
        return {"status": "error", "message": str(e)}
    audit_edit(res["sql"], "ok", res["row_count"], ms(), **who)
    return {"status": "ok", **res}