export function formatCell(v) {
  if (v === null || v === undefined) return "—";
  if (typeof v === "number") {
    return Number.isInteger(v)
      ? v.toLocaleString()
      : v.toLocaleString(undefined, { maximumFractionDigits: 2 });
  }
  return String(v);
}