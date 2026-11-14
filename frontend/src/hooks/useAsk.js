import { useState } from "react";
import { askQuestion, AuthError } from "../api";

const FAILURES = {
  rate_limit: { status: "error", message: "You're asking too fast. Wait a minute." },
  invalid: { status: "refused", message: "Please enter a question of up to 500 characters." },
  network: { status: "error", message: "Can't reach the backend. Is it running on port 8000?" },
  server: { status: "error", message: "The server had a problem. Please try again." },
  forbidden: { status: "error", message: "Your role is not allowed to do that." },
};

export default function useAsk(token, onAuthError) {
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const [count, setCount] = useState(0);      // used as a key to reset ResultCard

  async function ask(question) {
    const text = question.trim();
    if (!text || loading) return;
    setLoading(true);
    setResult(null);
    try {
      const r = await askQuestion(text, token);
      setResult(r.ok ? r.data : FAILURES[r.kind] ?? FAILURES.server);
      setCount((c) => c + 1);
    } catch (e) {
      if (e instanceof AuthError) onAuthError();
      else setResult(FAILURES.server);
    } finally {
      setLoading(false);
    }
  }

  return { result, loading, ask, count };
}