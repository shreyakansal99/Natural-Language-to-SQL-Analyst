import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from app.executor import ExecutionError, run_query
from app.pipeline import answer, audit_edit
from app.validator import ValidationError

app = FastAPI(title="Query-to-SQL Analyst")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)


class AskRequest(BaseModel):
    question: str = Field(min_length=1, max_length=500)


class RunSqlRequest(BaseModel):
    sql: str = Field(min_length=1, max_length=2000)


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/ask")
def ask(req: AskRequest):
    return answer(req.question)


@app.post("/run-sql")
def run_sql(req: RunSqlRequest):
    """User-edited SQL. Untrusted: it goes through the same validator and the
    same read-only database user as model-written SQL. No LLM is involved."""
    started = time.monotonic()
    ms = lambda: int((time.monotonic() - started) * 1000)
    try:
        res = run_query(req.sql)
    except ValidationError as e:
        audit_edit(req.sql, "rejected", 0, ms(), rule="validator")
        return {"status": "rejected", "message": str(e)}
    except ExecutionError as e:
        audit_edit(req.sql, "error", 0, ms(), rule="executor")
        return {"status": "error", "message": str(e)}
    audit_edit(res["sql"], "ok", res["row_count"], ms())
    return {"status": "ok", **res}