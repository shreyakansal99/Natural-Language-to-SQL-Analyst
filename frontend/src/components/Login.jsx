import { useState } from "react";
import { login } from "../api";

export default function Login({ onLogin }) {
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState(null);
  const [busy, setBusy] = useState(false);

  async function submit(e) {
    e.preventDefault();
    setBusy(true);
    setError(null);
    const r = await login(username, password);
    setBusy(false);
    if (r.ok) return onLogin(r.data);
    setError(
      r.kind === "rate_limit" ? "Too many attempts. Wait a minute."
      : r.kind === "network" ? "Can't reach the backend."
      : "Invalid username or password."
    );
  }

  return (
    <main className="app">
      <h1>Sales Data Analyst</h1>
      <form className="card login" onSubmit={submit}>
        <input placeholder="Username" value={username} autoComplete="username"
               onChange={(e) => setUsername(e.target.value)} />
        <input placeholder="Password" type="password" value={password}
               autoComplete="current-password" onChange={(e) => setPassword(e.target.value)} />
        <button disabled={busy || !username || !password}>{busy ? "Signing in…" : "Sign in"}</button>
        {error && <p className="sql-error">{error}</p>}
        <p className="note">Demo users: vera (viewer), alex (analyst), emma (EU manager).</p>
      </form>
    </main>
  );
}