import { useState } from "react";
import "./App.css";

const API_URL = "http://127.0.0.1:8000/ask";
const MAX_LEN = 500;

const EXAMPLES = [
  "Total revenue by region",
  "Top 5 product categories by revenue",
  "Monthly order count for 2025",
  "How many customers signed up per country?",
];

const BADGES = {
  ok: { label: "Answer", cls: "ok" },
  refused: { label: "Can't help with that", cls: "refused" },
  clarification: { label: "Need a bit more detail", cls: "clarify" },
  failed: { label: "Couldn't answer safely", cls: "failed" },
  error: { label: "Service problem", cls: "failed" },
};

function formatCell(v) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") {
    return Number.isInteger(v)
      ? v.toLocaleString()
      : v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return String(v);
}

function ResultTable({ columns, rows }) {
  if (!columns.length) return null;
  return (
    <div className="table-wrap">
      <table>
        <thead>
          <tr>{columns.map((c) => <th key={c}>{c}</th>)}</tr>
        </thead>
        <tbody>
          {rows.map((row, i) => (
            <tr key={i}>
              {row.map((v, j) => (
                <td key={j} className={typeof v === "number" ? "num" : ""}>
                  {formatCell(v)}
                </td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function SqlEditor({ originalSql, onResult }) {
  const [sql, setSql] = useState(originalSql);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const edited = sql.trim() !== originalSql.trim();

  async function run() {
    if (busy || !sql.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const res = await fetch("http://127.0.0.1:8000/run-sql", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ sql }),
      });
      if (res.status === 422) {
        setError("The SQL must be 1 to 2000 characters.");
      } else if (!res.ok) {
        setError("The server had a problem. Please try again.");
      } else {
        const data = await res.json();
        if (data.status === "ok") onResult(data, edited);
        else setError(data.message);
      }
    } catch {
      setError("Can't reach the backend. Is it running on port 8000?");
    } finally {
      setBusy(false);
    }
  }

  return (
    <>
      <textarea
        className="sql-editor"
        value={sql}
        onChange={(e) => setSql(e.target.value)}
        rows={Math.min(12, Math.max(4, sql.split("\n").length + 1))}
        spellCheck={false}
        maxLength={2000}
        aria-label="SQL query"
      />
      <div className="sql-actions">
        <button onClick={run} disabled={busy || !sql.trim()}>
          {busy ? "Running…" : "Run edited SQL"}
        </button>
        <button className="secondary" onClick={() => { setSql(originalSql); setError(null); }}
          disabled={!edited}>
          Reset
        </button>
        <span className="note">Read-only: only SELECT on the four sales views.</span>
      </div>
      {error && <p className="sql-error">{error}</p>}
    </>
  );
}

export default function App() {
  const [question, setQuestion] = useState("");
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [editedRun, setEditedRun] = useState(null);

  async function ask(q) {
    const text = q.trim();
    if (!text || loading) return;
    setLoading(true);
    setResult(null);
    setEditedRun(null);
    try {
      const res = await fetch(API_URL, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ question: text }),
      });
      if (res.status === 422) {
        setResult({ status: "refused", message: "Please enter a question of up to 500 characters." });
      } else if (!res.ok) {
        setResult({ status: "error", message: "The server had a problem. Please try again." });
      } else {
        setResult(await res.json());
      }
    } catch {
      setResult({ status: "error", message: "Can't reach the backend. Is it running on port 8000?" });
    } finally {
      setLoading(false);
    }
  }

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      ask(question);
    }
  }

  const badge = result ? BADGES[result.status] ?? BADGES.error : null;

  return (
    <main className="app">
      <h1>Sales Data Analyst</h1>
      <p className="sub">
        Ask a question in plain English. The assistant writes read-only SQL, checks it, runs it, and explains the result.
      </p>

      <div className="ask">
        <textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={onKeyDown}
          maxLength={MAX_LEN}
          rows={2}
          placeholder="e.g. Total revenue by region"
          aria-label="Your question"
        />
        <button onClick={() => ask(question)} disabled={loading || !question.trim()}>
          {loading ? "Thinking…" : "Ask"}
        </button>
      </div>
      <div className="counter">{question.length}/{MAX_LEN}</div>

      <div className="chips">
        {EXAMPLES.map((ex) => (
          <button
            key={ex}
            className="chip"
            disabled={loading}
            onClick={() => { setQuestion(ex); ask(ex); }}
          >
            {ex}
          </button>
        ))}
      </div>

      {loading && <div className="card muted">Writing and checking the query…</div>}

      {result && (
        <section className="card">
          <span className={`badge ${badge.cls}`}>{badge.label}</span>

          {result.status !== "ok" && <p className="message">{result.message}</p>}

          {editedRun ? (
            <>
              <p className="edited-banner">
                Showing results of <strong>your edited SQL</strong>. The explanation above
                describes the AI's original query.
              </p>
              <ResultTable columns={editedRun.columns} rows={editedRun.rows} />
              {editedRun.truncated && (
                <p className="note">Showing the first {editedRun.row_count} rows only.</p>
              )}
              {editedRun.row_count === 0 && <p className="note">The query ran but returned no rows.</p>}
            </>
          ) : (
            <>
              <ResultTable columns={result.columns} rows={result.rows} />
              {result.truncated && (
                <p className="note">Showing the first {result.row_count} rows only. Narrow the question to see the rest.</p>
              )}
              {result.row_count === 0 && <p className="note">The query ran but returned no rows.</p>}
            </>
          )}

          <details>
            <summary>Show / edit the SQL</summary>
            <SqlEditor
              key={result.sql}
              originalSql={result.sql}
              onResult={(data, wasEdited) => setEditedRun(wasEdited ? data : null)}
            />
            <p className="note">
              {result.row_count} row{result.row_count === 1 ? "" : "s"} from the AI's query
              {result.attempts > 1 ? ` · took ${result.attempts} attempts` : ""}
            </p>
          </details>

          {result.status === "failed" && result.sql && (
            <details>
              <summary>Last attempted SQL (rejected or failed)</summary>
              <pre>{result.sql}</pre>
            </details>
          )}
        </section>
      )}
    </main>
  );
}