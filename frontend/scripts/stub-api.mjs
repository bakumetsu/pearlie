/* global console, process, URL */
// Dev-only fixture API for the UI checks. No real Stash, Stump or site calls, no secrets.
// Start: node scripts/stub-api.mjs [port]  (default 8010; Vite: --config vite.stub.config.ts)
// /__expire: debug key expired. /__error: real 500 on it and on later GETs; DELETE debug-key clears it.
import http from "node:http";
import { fileURLToPath } from "node:url";

const JSON_HEADERS = { "content-type": "application/json" };
const TTL = { never: null, "1h": 3600e3, "24h": 86400e3, "7d": 7 * 86400e3 };
const OFF = { state: "off", id: null, created_at: null, expires_at: null, last_used_at: null, uses_approx: 0 };

// Merged Discover row fixtures (D-38). Flat placeholder thumbs, no real site.
const RAIL = [
  ["danbooru", "Danbooru", "#4f8cff"],
  ["gelbooru", "Gelbooru", "#3fb97f"],
  ["rule34", "Rule34", "#d9a441"],
  ["nhentai", "nhentai", "#e0568a"],
];
const thumb = (color, label) =>
  "data:image/svg+xml," +
  encodeURIComponent(
    `<svg xmlns="http://www.w3.org/2000/svg" width="300" height="400"><rect width="300" height="400" fill="${color}" opacity="0.35"/><text x="150" y="210" font-size="40" text-anchor="middle" fill="#888">${label}</text></svg>`,
  );
const webItem = (source, color, n) => ({
  source,
  post_id: String(1000 + n),
  thumb_url: thumb(color, `${source[0].toUpperCase()}${n}`),
  preview_url: thumb(color, `${source[0].toUpperCase()}${n}`),
  media_kind: "image",
  title: null,
  tags: [],
  width: 300,
  height: 400,
  page_count: null,
  target: "stash",
  saveable: true,
  saved: null,
  owned: false,
  blur: null,
  gif_url: null,
});
// Scenarios: ok, partial (Gelbooru failed), slow (Rule34 late: pending on the first call), failed, empty, loading (never answers).
// Set with /__merged?mode=<name>; the default is ok.
function mergedRow(mode, have, call) {
  const per = 12;
  const states = Object.fromEntries(RAIL.map(([id]) => [id, "ok"]));
  if (mode === "partial") states.gelbooru = "error";
  if (mode === "slow") states.rule34 = "pending";
  if (mode === "failed") for (const id of Object.keys(states)) states[id] = "error";
  if (mode === "empty") for (const id of Object.keys(states)) states[id] = "empty";
  const slowDone = mode === "slow" && call > 1; // the poll after the first answer
  if (slowDone) states.rule34 = "ok";
  const lists = RAIL.map(([id, , color]) => (states[id] === "ok" ? Array.from({ length: per }, (_, i) => webItem(id, color, i + 1)) : []));
  // `have` sites keep their rounds first; a late site is appended after them.
  const order = RAIL.map((_, i) => i).sort((a, b) => Number(have.includes(RAIL[b][0])) - Number(have.includes(RAIL[a][0])));
  const items = [];
  for (let i = 0; i < per; i++) for (const k of order) if (lists[k][i]) items.push(lists[k][i]);
  return {
    items,
    sites: RAIL.map(([id, title]) => ({
      id,
      title,
      state: states[id],
      count: states[id] === "ok" ? per : 0,
      message: states[id] === "error" ? "The site did not answer" : null,
    })),
    hidden: mode === "empty" ? 3 : 0,
    pending: states.rule34 === "pending",
  };
}

export function createStub() {
  let key = { ...OFF };
  let failing = false;
  let mergedMode = "ok";
  let mergedCalls = 0;
  return http.createServer((req, res) => {
    const url = new URL(req.url, "http://stub");
    let body = "";
    req.on("data", (chunk) => (body += chunk));
    req.on("end", () => {
      const send = (status, payload) => {
        res.writeHead(status, JSON_HEADERS);
        res.end(payload === undefined ? undefined : JSON.stringify(payload));
      };
      if (url.pathname === "/__error") {
        failing = true;
        return send(500, { detail: "stub error" });
      }
      if (url.pathname === "/__expire") {
        key = { ...key, state: "expired", expires_at: new Date(Date.now() - 2 * 3600e3).toISOString() };
        return send(200, { ok: true });
      }
      if (url.pathname === "/__merged") {
        mergedMode = url.searchParams.get("mode") ?? "ok";
        mergedCalls = 0;
        return send(200, { mode: mergedMode });
      }
      if (url.pathname === "/api/discover/merged") {
        if (mergedMode === "loading") return; // never answers: the loading frame
        const have = (url.searchParams.get("have") ?? "").split(",").filter(Boolean);
        return send(200, mergedRow(mergedMode, have, ++mergedCalls));
      }
      if (url.pathname === "/api/discover/merged/list") {
        const page = Number(url.searchParams.get("page") ?? "1");
        const items = [];
        for (let i = 0; i < 12; i++) for (const [id, , color] of RAIL) items.push(webItem(id, color, (page - 1) * 12 + i + 1));
        return send(200, { items, page, next_page: page < 3 ? page + 1 : null, sites: RAIL.map(([id]) => ({ id, state: "ok", count: 12 })) });
      }
      if (url.pathname === "/api/options/debug-key") {
        if (req.method === "DELETE") {
          key = { ...OFF };
          failing = false;
          res.writeHead(204);
          return res.end();
        }
        if (failing) return send(500, { detail: "stub error" });
        if (req.method === "GET") return send(200, key);
        if (req.method === "POST") {
          let ttl;
          try {
            ttl = JSON.parse(body || "{}").ttl ?? "24h";
          } catch {
            return send(400, { detail: "bad json" });
          }
          if (!(ttl in TTL)) return send(400, { detail: "bad ttl" });
          const now = Date.now();
          key = {
            state: "active",
            id: "dk_7f3a91",
            created_at: new Date(now).toISOString(),
            expires_at: TTL[ttl] === null ? null : new Date(now + TTL[ttl]).toISOString(),
            last_used_at: new Date(now - 420e3).toISOString(),
            uses_approx: 12,
          };
          return send(200, { key: "pdk_stub_not_a_secret", id: key.id, expires_at: key.expires_at });
        }
      }
      if (failing) return send(500, { detail: "stub error" });
      send(200, {});
    });
  });
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const port = Number(process.argv[2] ?? 8010);
  createStub().listen(port, "127.0.0.1", () => console.log(`stub api on 127.0.0.1:${port}`));
}
