import { API } from "./config";

export class AuthError extends Error {}

async function post(path, body, token) {
  const headers = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  let res;
  try {
    res = await fetch(`${API}${path}`, { method: "POST", headers, body: JSON.stringify(body) });
  } catch {
    return { ok: false, kind: "network" };
  }
  if (res.status === 401 && token) throw new AuthError();
  if (res.status === 429) return { ok: false, kind: "rate_limit" };
  if (res.status === 403) return { ok: false, kind: "forbidden" };
  if (res.status === 422) return { ok: false, kind: "invalid" };
  if (!res.ok) return { ok: false, kind: "server" };
  return { ok: true, data: await res.json() };
}

export const login = (username, password) => post("/login", { username, password });
export const askQuestion = (question, token) => post("/ask", { question }, token);
export const runSql = (sql, token) => post("/run-sql", { sql }, token);