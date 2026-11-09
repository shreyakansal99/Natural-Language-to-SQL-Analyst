"""Execution-accuracy evaluation for the NL-to-SQL pipeline.

Run from backend/:
    python -m eval.run_eval                  # all questions
    python -m eval.run_eval --category date  # one category
    python -m eval.run_eval --ids s1,g3      # specific questions

Compares RESULT SETS against the gold query's result, never the SQL text.
To compare models:  MISTRAL_MODEL=other-model python -m eval.run_eval
(an exported env var overrides .env).
"""
import argparse
import itertools
import json
import time
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from app import pipeline
from app.config import MISTRAL_MODEL
from app.executor import run_query

HERE = Path(__file__).resolve().parent
QUESTIONS_FILE = HERE / "eval_questions.json"
RESULTS_DIR = HERE / "results"

FLOAT_DIGITS = 1        # numbers are compared after rounding to 1 decimal
MAX_COMBO_COLUMNS = 8   # cap for the "extra columns" search

TOLERANCE = 0.01          # 1% relative (absolute 0.01 for values under 1)
MAX_COMBO_COLUMNS = 8


# ---------------------------------------------------------------- comparison
def _num(v):
    if isinstance(v, bool) or v is None:
        return None
    return float(v) if isinstance(v, (int, float)) else None


def _cells_equal(a, b) -> bool:
    x, y = _num(a), _num(b)
    if x is not None and y is not None:
        return abs(x - y) <= TOLERANCE * max(1.0, abs(y))
    return str(a).strip().lower() == str(b).strip().lower()


def _rows_equal(r1, r2) -> bool:
    """Same cells in any column order."""
    if len(r1) != len(r2):
        return False
    remaining = list(r2)
    for a in r1:
        for i, b in enumerate(remaining):
            if _cells_equal(a, b):
                del remaining[i]
                break
        else:
            return False
    return True


def _sets_equal(rows_a, rows_b, ordered: bool) -> bool:
    if len(rows_a) != len(rows_b):
        return False
    if ordered:
        return all(_rows_equal(a, b) for a, b in zip(rows_a, rows_b))
    remaining = list(rows_b)
    for a in rows_a:
        for i, b in enumerate(remaining):
            if _rows_equal(a, b):
                del remaining[i]
                break
        else:
            return False
    return True


def compare(gold_rows, got_rows, ordered=False):
    """Return 'exact', 'extra_columns', or None (mismatch).

    Ignores column names, column order, and (unless ordered) row order.
    Numbers match within TOLERANCE. 'extra_columns' means the answer
    contained all the gold columns plus more.
    """
    if len(gold_rows) != len(got_rows):
        return None
    if not gold_rows:
        return "exact"

    n_gold, n_got = len(gold_rows[0]), len(got_rows[0])
    if n_got == n_gold:
        return "exact" if _sets_equal(gold_rows, got_rows, ordered) else None
    if n_gold < n_got <= MAX_COMBO_COLUMNS:
        for cols in itertools.combinations(range(n_got), n_gold):
            subset = [[r[i] for i in cols] for r in got_rows]
            if _sets_equal(gold_rows, subset, ordered):
                return "extra_columns"
    return None


# ---------------------------------------------------------------- running
def ask(question, retries=2, wait=5.0):
    """Call the pipeline; retry transient service errors (rate limits)."""
    for attempt in range(retries + 1):
        res = pipeline.answer(question)
        if res["status"] != "error" or attempt == retries:
            return res
        time.sleep(wait)


def evaluate_one(item) -> dict:
    rec = {"id": item["id"], "category": item["category"], "question": item["question"]}
    try:
        gold = run_query(item["gold_sql"])
    except Exception as e:                      # gold must pass our own validator
        rec.update(outcome="gold_error", detail=f"{type(e).__name__}: {e}",
                   gold_sql=item["gold_sql"])
        return rec

    started = time.monotonic()
    res = ask(item["question"])
    rec.update(status=res["status"], attempts=res["attempts"], sql=res["sql"],
               seconds=round(time.monotonic() - started, 1),
               assumptions=res.get("assumptions", []))
    if res["status"] == "error":
        rec.update(outcome="inconclusive", detail="LLM unavailable (rate limit). Re-run this id.")
        return rec

    if res["status"] != "ok":
        rec.update(outcome="no_answer", detail=res.get("message"))
        return rec

    match = compare(gold["rows"], res["rows"], item.get("ordered", False))
    if match:
        rec.update(outcome="correct", match=match)
    else:
        rec.update(outcome="wrong_result", gold_sql=item["gold_sql"],
                   detail=(f"gold: {gold['row_count']} rows x {len(gold['columns'])} cols, "
                           f"got: {res['row_count']} rows x {len(res['columns'])} cols"))
    return rec


def pct(a, b):
    return f"{100 * a / b:.0f}%" if b else "n/a"


def summarize(records) -> dict:
    ev = [r for r in records if r["outcome"] not in ("gold_error", "inconclusive")]
    by_cat = defaultdict(lambda: {"n": 0, "correct": 0})
    for r in ev:
        by_cat[r["category"]]["n"] += 1
        by_cat[r["category"]]["correct"] += r["outcome"] == "correct"
    correct = [r for r in ev if r["outcome"] == "correct"]
    return {
        "evaluated": len(ev),
        "gold_errors": len(records) - len(ev),
        "correct": len(correct),
        "accuracy": round(len(correct) / len(ev), 3) if ev else None,
        "answered": sum(r["outcome"] in ("correct", "wrong_result") for r in ev),
        "wrong_result": sum(r["outcome"] == "wrong_result" for r in ev),
        "no_answer": sum(r["outcome"] == "no_answer" for r in ev),
        "correct_first_try": sum(r["attempts"] == 1 for r in correct),
        "recovered_by_retry": sum(r["attempts"] > 1 for r in correct),
        "by_category": dict(by_cat),
        "inconclusive": sum(r["outcome"] == "inconclusive" for r in records),
    }


def print_report(records, summary, model):
    print(f"\nModel: {model}")
    print(f"{'category':<14}{'n':>4}{'correct':>9}{'accuracy':>10}")
    for cat, d in summary["by_category"].items():
        print(f"{cat:<14}{d['n']:>4}{d['correct']:>9}{pct(d['correct'], d['n']):>10}")
    s = summary
    print(f"{'OVERALL':<14}{s['evaluated']:>4}{s['correct']:>9}{pct(s['correct'], s['evaluated']):>10}")
    print(f"\nWrong result (ran, looked fine, wrong answer): {s['wrong_result']}")
    print(f"No answer (refused / clarification / failed):   {s['no_answer']}")
    print(f"Correct on first try: {s['correct_first_try']}   recovered by retry: {s['recovered_by_retry']}")
    if s["gold_errors"]:
        print(f"GOLD QUERY ERRORS: {s['gold_errors']} (fix these, they are not scored)")
    if s["inconclusive"]:
        print(f"INCONCLUSIVE (rate limited, not scored): {s['inconclusive']}")

    bad = [r for r in records if r["outcome"] not in ("correct",)]
    if bad:
        print("\nProblems:")
    for r in bad:
        print(f"\n[{r['id']}] {r['outcome']}: {r['question']}")
        if r.get("sql"):
            print(f"   model SQL: {r['sql']}")
        if r.get("gold_sql"):
            print(f"   gold SQL:  {r['gold_sql']}")
        if r.get("detail"):
            print(f"   detail:    {r['detail']}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--category")
    ap.add_argument("--ids", help="comma-separated question ids")
    ap.add_argument("--delay", type=float, default=1.0, help="seconds between questions")
    args = ap.parse_args()

    items = json.loads(QUESTIONS_FILE.read_text())
    if args.category:
        items = [i for i in items if i["category"] == args.category]
    if args.ids:
        wanted = set(args.ids.split(","))
        items = [i for i in items if i["id"] in wanted]
    if not items:
        raise SystemExit("No questions selected.")

    # Skip the explanation LLM calls (not needed for accuracy) and keep
    # eval traffic out of the normal audit log.
    RESULTS_DIR.mkdir(exist_ok=True)
    pipeline.generate_text = lambda system, user: ""
    pipeline.AUDIT_FILE = RESULTS_DIR / "eval_audit.jsonl"

    records = []
    for n, item in enumerate(items, 1):
        rec = evaluate_one(item)
        records.append(rec)
        print(f"[{n}/{len(items)}] {item['id']:<4} {rec['outcome']}")
        time.sleep(args.delay)

    summary = summarize(records)
    print_report(records, summary, MISTRAL_MODEL)

    out = RESULTS_DIR / f"eval_{datetime.now():%Y%m%d_%H%M%S}.json"
    out.write_text(json.dumps({"model": MISTRAL_MODEL, "summary": summary,
                               "records": records}, indent=2, default=str))
    print(f"\nSaved {out}")


if __name__ == "__main__":
    main()