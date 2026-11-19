export function expiresLabel(expiresAt: string, now: number = Date.now()): string {
  const ms = Date.parse(expiresAt) - now;
  if (Number.isNaN(ms)) return "";
  if (ms <= 0) return "Expired";
  const D = 86_400_000;
  if (ms < D) return "Expires today";
  const d = Math.floor(ms / D);
  return `Expires in ${d} ${d === 1 ? "day" : "days"}`;
}

export function daysLeft(expiresAt: string, now: number = Date.now()): number {
  const ms = Date.parse(expiresAt) - now;
  if (Number.isNaN(ms) || ms <= 0) return 0;
  return Math.ceil(ms / 86_400_000);
}

export function sideOf(kind: string): "Stash" | "Stump" {
  return kind === "series" || kind === "book" ? "Stump" : "Stash";
}

export function formatSize(bytes: number): string {
  if (bytes < 1024 * 1024) return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  if (bytes < 1024 ** 3) return `${(bytes / 1024 ** 2).toFixed(1)} MB`;
  return `${(bytes / 1024 ** 3).toFixed(1)} GB`;
}
