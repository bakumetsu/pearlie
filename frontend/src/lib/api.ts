export type State = "ok" | "down" | "not_configured";

export type Health = {
  status: "ok" | "degraded";
  db: "ok" | "error";
  stash: { state: State; version: string | null };
  komga: { state: State; version: string | null };
  mounts: { name: string; state: State }[];
  sites: { id: string; state: State }[];
};

export async function getHealth(): Promise<Health> {
  const res = await fetch("/api/health");
  if (!res.ok) {
    throw new Error(`HTTP ${res.status}`);
  }
  return res.json();
}
