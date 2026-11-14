import { useState } from "react";
import { runSql } from "../api";

const MESSAGES = {
  invalid: "The SQL must be 1 to 2000 characters.",
  forbidden: "Your role can't run edited SQL.",
  rate_limit: "Too many requests. Wait a minute.",
  network: "Can't reach the backend. Is it running on port 8000?",
  server: "The server had a problem. Please try again.",
};

export default function SqlEditor({ originalSql, token, onResult, onAuthError }) {
  const [sql, setSql] = useState(originalSql);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState(null);
  const edited = sql.trim() !== originalSql.trim();

  async function run() {
    if (busy || !sql.trim()) return;
    setBusy(true);
    setError(null);
    try {
      const r = await runSql(sql, token);
      if (!r.ok) setError(MESSAGES[r.kind] ?? MESSAGES.server);
      else if (r.data.status === "ok") onResult(r.data, edited);
      else setError(r.data.message);
    } catch {
      onAuthError();                     // 401: token expired
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
        <button className="secondary" disabled={!edited}
                onClick={() => { setSql(originalSql); setError(null); }}>
          Reset
        </button>
        <span className="note">Read-only: only SELECT on the views your role can see.</span>
      </div>
      {error && <p className="sql-error">{error}</p>}
    </>
  );
}