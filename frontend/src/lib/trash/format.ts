export function expiresLabel(expiresAt: string, now: number = Date.now()): string {
  const ms = Date.parse(expiresAt) - now;
  if (Number.isNaN(ms)) return "";
  if (ms <= 0) return "Expired";
  const H = 3_600_000;
  const D = 86_400_000;
  if (ms < H) return "Expires in under 1 h";
  if (ms < 2 * D) return `Expires in ${Math.floor(ms / H)} h`;
  return `Expires in ${Math.floor(ms / D)} d`;
}
