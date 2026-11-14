import { useState } from "react";
import { EXAMPLES, MAX_LEN } from "../config";

export default function QuestionBox({ loading, onAsk }) {
  const [question, setQuestion] = useState("");

  function onKeyDown(e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      onAsk(question);
    }
  }

  return (
    <>
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
        <button onClick={() => onAsk(question)} disabled={loading || !question.trim()}>
          {loading ? "Thinking…" : "Ask"}
        </button>
      </div>
      <div className="counter">{question.length}/{MAX_LEN}</div>

      <div className="chips">
        {EXAMPLES.map((ex) => (
          <button key={ex} className="chip" disabled={loading}
                  onClick={() => { setQuestion(ex); onAsk(ex); }}>
            {ex}
          </button>
        ))}
      </div>
    </>
  );
}