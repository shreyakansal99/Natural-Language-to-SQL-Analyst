export const API = "http://127.0.0.1:8000";
export const MAX_LEN = 500;

export const EXAMPLES = [
  "Total revenue by region",
  "Top 5 product categories by revenue",
  "Monthly order count for 2025",
  "How many customers signed up per country?",
];

export const BADGES = {
  ok: { label: "Answer", cls: "ok" },
  refused: { label: "Can't help with that", cls: "refused" },
  clarification: { label: "Need a bit more detail", cls: "clarify" },
  failed: { label: "Couldn't answer safely", cls: "failed" },
  error: { label: "Service problem", cls: "failed" },
};