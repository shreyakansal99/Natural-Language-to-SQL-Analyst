"""Orchestration: guardrail -> generate -> validate+execute (retry) -> explain -> audit."""
import json
import logging
import time
from datetime import datetime, timezone
from pathlib import Path

from app.executor import ExecutionError, run_query
from app.guardrails import GuardrailRefusal, check_question, redact_text, redact_value
from app.llm import generate_json, generate_text
from app.prompts import EXPLAIN_SYSTEM_PROMPT, build_sql_system_prompt, build_user_message
from app.validator import ValidationError
from contextvars import ContextVar
from app.roles import DEFAULT_ROLE

log = logging.getLogger("pipeline")

MAX_ATTEMPTS = 3          # first try + 2 retries
PREVIEW_ROWS = 20
AUDIT_FILE = Path(__file__).resolve().parent.parent / "logs" / "audit.jsonl"
STATUS_WORDS = ("cancel", "refund", "complet", "ship", "pending", "status")

_ctx: ContextVar = ContextVar("ctx", default={"user": "anonymous", "role": "analyst"})


def _hidden_filter_note(question: str, sql: str) -> str | None:
    s, q = sql.lower(), question.lower()
    if "status" in s and " where " in s and not any(w in q for w in STATUS_WORDS):
        return "Note: the query filters on order status, which the question did not ask for."
    return None


def _audit(entry: dict) -> None:
    try:
        AUDIT_FILE.parent.mkdir(exist_ok=True)
        with AUDIT_FILE.open("a") as f:
            f.write(json.dumps(entry) + "\n")
    except OSError:
        log.exception("could not write audit log")


def audit_edit(sql, status, row_count, ms, rule=None, user="anonymous", role="analyst"):
    _audit({
        "ts": datetime.now(timezone.utc).isoformat(),
        "source": "user_edit",
        "status": status,
        "guardrail": rule,
        "sql": sql[:2000],
        "row_count": row_count,
        "ms": ms,
        "user": user, 
        "role": role
    })


def _finish(question, started, status, **fields) -> dict:
    result = {"status": status, "message": None, "sql": None, "columns": [], "rows": [],
              "row_count": 0, "truncated": False, "explanation": None, "attempts": 0,
              "assumptions": [], "source": "ask"}
    result.update(fields)
    _audit({
        "ts": datetime.now(timezone.utc).isoformat(),
        "question": redact_text(str(question))[:300],
        "status": status,
        "guardrail": fields.get("guardrail"),
        "sql": result["sql"],
        "attempts": result["attempts"],
        "row_count": result["row_count"],
        "ms": int((time.monotonic() - started) * 1000),
        "user": _ctx.get()["user"],
        "role": _ctx.get()["role"],
    })
    result.pop("guardrail", None)
    return result


def _explain(question: str, res: dict) -> str:
    if res["row_count"] == 0:
        return "The query ran successfully but returned no rows."

    # Single number: format in code, no LLM needed (can't hallucinate)
    if res["row_count"] == 1 and len(res["columns"]) == 1:
        value = res["rows"][0][0]
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            label = res["columns"][0].replace("_", " ").capitalize()
            shown = f"{value:,}" if isinstance(value, int) else f"{value:,.2f}"
            return f"{label}: {shown}"

    preview = {"columns": res["columns"], "rows": res["rows"][:PREVIEW_ROWS],
               "total_rows": res["row_count"], "truncated": res["truncated"]}
    # escape < and > so a data value can't fake a closing </data> tag
    data = json.dumps(preview).replace("<", "\\u003c").replace(">", "\\u003e")
    try:
        text = generate_text(EXPLAIN_SYSTEM_PROMPT,
                             f"<question>{question}</question>\n<data>{data}</data>")
        return redact_text(text)
    except Exception:
        log.exception("explanation failed")
        return "The query succeeded, but I couldn't write an explanation this time."


def answer(raw_question: str, role=None, username: str = "anonymous") -> dict:
    role = role or DEFAULT_ROLE
    _ctx.set({"user": username, "role": role.name})
    started = time.monotonic()

    try:
        question = check_question(raw_question)
    except GuardrailRefusal as e:
        return _finish(raw_question, started, "refused", message=str(e), guardrail=e.rule)

    feedback, last_rule, sql, result = None, None, None, None
    attempts = 0
    for attempts in range(1, MAX_ATTEMPTS + 1):
        try:
            plan = generate_json(build_sql_system_prompt(role), build_user_message(question, feedback))
        except Exception:
            log.exception("LLM call failed")
            return _finish(question, started, "error", attempts=attempts,
                           message="The AI service is unavailable right now. Please try again.")

        if not isinstance(plan, dict):
            feedback, last_rule = "Your reply was not a JSON object.", "bad_format"
            continue
        if plan.get("needs_clarification"):
            return _finish(question, started, "clarification", attempts=attempts,
                           message=str(plan.get("clarification_question") or "Could you be more specific?"))
        if plan.get("cannot_answer_reason"):
            return _finish(question, started, "refused", attempts=attempts, guardrail="model_refusal",
                           message=str(plan["cannot_answer_reason"]))

        sql = plan.get("sql")
        if not isinstance(sql, str) or not sql.strip():
            feedback, last_rule = "The 'sql' field was empty.", "bad_format"
            continue

        try:
            result = run_query(sql, role)          # validates, then executes
            note = _hidden_filter_note(question, result["sql"])
            if note and attempts < MAX_ATTEMPTS:
                feedback = ("Your query filters on order status, but the question did not ask for that. "
                            "Remove the status filter and return the JSON object again.\n"
                            f"Your SQL: {sql}")
                last_rule, result = "hidden_filter", None
                continue
            break
            break
        except ValidationError as e:
            feedback, last_rule = f"Rejected by the validator: {e}\nYour SQL: {sql}", "validator"
        except ExecutionError as e:
            feedback, last_rule = f"Failed at run time: {e}\nYour SQL: {sql}", "executor"

    if result is None:
        return _finish(question, started, "failed", attempts=attempts, sql=sql, guardrail=last_rule,
                       message="I couldn't produce a safe, working query for that question. "
                               "Try rephrasing it or narrowing it down.")

    result["rows"] = [[redact_value(v) for v in row] for row in result["rows"]]
    explanation = _explain(question, result)

    assumptions = [str(a)[:200] for a in (plan.get("assumptions") or [])
                   if isinstance(a, (str, int, float))][:5]
    note = _hidden_filter_note(question, result["sql"])
    if note:
        assumptions.append(note)

    return _finish(question, started, "ok", attempts=attempts, sql=result["sql"],
                   columns=result["columns"], rows=result["rows"], row_count=result["row_count"],
                   truncated=result["truncated"], explanation=explanation,
                   assumptions=assumptions)
