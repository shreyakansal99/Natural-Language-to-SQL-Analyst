from app import pipeline

GOOD = {"sql": "SELECT region, COUNT(*) AS n FROM orders_safe GROUP BY region"}


def fake_text(system, user):
    return "Orders are split across three regions."


def test_retry_recovers_from_a_rejected_query(monkeypatch):
    calls = []

    def fake_json(system, user):
        calls.append(user)
        return {"sql": "SELECT * FROM customers"} if len(calls) == 1 else GOOD

    monkeypatch.setattr(pipeline, "generate_json", fake_json)
    monkeypatch.setattr(pipeline, "generate_text", fake_text)
    r = pipeline.answer("orders per region")
    assert r["status"] == "ok" and r["attempts"] == 2
    assert "rejected" in calls[1].lower()


def test_model_tricked_into_drop_is_blocked_and_gives_up(monkeypatch):
    monkeypatch.setattr(pipeline, "generate_json", lambda s, u: {"sql": "DROP TABLE orders_safe"})
    r = pipeline.answer("orders per region")
    assert r["status"] == "failed" and r["attempts"] == pipeline.MAX_ATTEMPTS
    assert r["rows"] == []


def test_clarification_is_passed_through(monkeypatch):
    monkeypatch.setattr(pipeline, "generate_json", lambda s, u: {
        "needs_clarification": True, "clarification_question": "Which year?"})
    r = pipeline.answer("show sales")
    assert r["status"] == "clarification" and r["message"] == "Which year?"


def test_guardrail_refusal_never_reaches_the_llm(monkeypatch):
    def boom(*a):
        raise AssertionError("LLM should not be called")
    monkeypatch.setattr(pipeline, "generate_json", boom)
    assert pipeline.answer("Delete all customers")["status"] == "refused"


def test_llm_outage_is_handled(monkeypatch):
    def boom(*a):
        raise RuntimeError("network down")
    monkeypatch.setattr(pipeline, "generate_json", boom)
    assert pipeline.answer("orders per region")["status"] == "error"


def test_hidden_status_filter_is_flagged():
    from app.pipeline import _hidden_filter_note
    sql = "SELECT AVG(total) FROM orders_safe WHERE status <> 'cancelled'"
    assert _hidden_filter_note("Average order value by country", sql)
    assert _hidden_filter_note("Average value of cancelled orders", sql) is None