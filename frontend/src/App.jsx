import { useState } from "react";
import "./App.css";
import Login from "./components/Login";
import QuestionBox from "./components/QuestionBox";
import ResultCard from "./components/ResultCard";
import UserBar from "./components/UserBar";
import useAsk from "./hooks/useAsk";

function Workspace({ auth, onLogout }) {
  const { result, loading, ask, count } = useAsk(auth.token, onLogout);

  return (
    <main className="app">
      <UserBar auth={auth} onLogout={onLogout} />
      <h1>Sales Data Analyst</h1>
      <p className="sub">
        Ask a question in plain English. The assistant writes read-only SQL, checks it,
        runs it, and explains the result.
      </p>

      <QuestionBox loading={loading} onAsk={ask} />

      {loading && <div className="card muted">Writing and checking the query…</div>}
      {result && <ResultCard key={count} result={result} auth={auth} onAuthError={onLogout} />}
    </main>
  );
}

export default function App() {
  const [auth, setAuth] = useState(null);     // in memory only, never localStorage
  if (!auth) return <Login onLogin={setAuth} />;
  return <Workspace auth={auth} onLogout={() => setAuth(null)} />;
}