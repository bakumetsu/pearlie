export function expiresLabel(expiresAt: string, now: number = Date.now()): string {
  const ms = Date.parse(expiresAt) - now;
  if (Number.isNaN(ms)) return "";
  if (ms <= 0) return "Expired";
  const D = 86_400_000;
  if (ms < D) return "Expires today";
  const d = Math.floor(ms / D);
  return `Expires in ${d} ${d === 1 ? "day" : "days"}`;
}
