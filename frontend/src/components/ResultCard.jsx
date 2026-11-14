import { useState } from "react";
import { BADGES } from "../config";
import ResultTable from "./ResultTable";
import SqlEditor from "./SqlEditor";

function Rows({ data, nudge }) {
  return (
    <>
      <ResultTable columns={data.columns} rows={data.rows} />
      {data.truncated && (
        <p className="note">Showing the first {data.row_count} rows only.{nudge}</p>
      )}
      {data.row_count === 0 && <p className="note">The query ran but returned no rows.</p>}
    </>
  );
}

export default function ResultCard({ result, auth, onAuthError }) {
  const [editedRun, setEditedRun] = useState(null);
  const badge = BADGES[result.status] ?? BADGES.error;
  const ok = result.status === "ok";

  return (
    <section className="card">
      <span className={`badge ${badge.cls}`}>{badge.label}</span>

      {!ok && <p className="message">{result.message}</p>}

      {ok && (
        <>
          {result.explanation && <p className="explanation">{result.explanation}</p>}

          {result.assumptions?.length > 0 && (
            <div className="assumptions">
              <strong>Assumptions</strong>
              <ul>{result.assumptions.map((a, i) => <li key={i}>{a}</li>)}</ul>
            </div>
          )}

          {editedRun ? (
            <>
              <p className="edited-banner">
                Showing results of <strong>your edited SQL</strong>. The explanation above
                describes the AI's original query.
              </p>
              <Rows data={editedRun} nudge="" />
            </>
          ) : (
            <Rows data={result} nudge=" Narrow the question to see the rest." />
          )}

          <details>
            <summary>{auth.can_edit ? "Show / edit the SQL" : "Show the SQL"}</summary>
            {auth.can_edit ? (
              <SqlEditor
                key={result.sql}
                originalSql={result.sql}
                token={auth.token}
                onAuthError={onAuthError}
                onResult={(data, wasEdited) => setEditedRun(wasEdited ? data : null)}
              />
            ) : (
              <pre>{result.sql}</pre>
            )}
            <p className="note">
              {result.row_count} row{result.row_count === 1 ? "" : "s"} from the AI's query
              {result.attempts > 1 ? ` · took ${result.attempts} attempts` : ""}
            </p>
          </details>
        </>
      )}

      {result.status === "failed" && result.sql && (
        <details>
          <summary>Last attempted SQL (rejected or failed)</summary>
          <pre>{result.sql}</pre>
        </details>
      )}
    </section>
  );
}