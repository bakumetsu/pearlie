/* global console, process, URL */
// Dev-only fixture API for the UI checks. No real Stash, Stump or site calls, no secrets.
// Start: node scripts/stub-api.mjs [port]  (default 8010; Vite: --config vite.stub.config.ts)
// /__expire: debug key expired. /__error: real 500 on it and on later GETs; DELETE debug-key clears it.
import http from "node:http";
import { fileURLToPath } from "node:url";

const JSON_HEADERS = { "content-type": "application/json" };
const TTL = { never: null, "1h": 3600e3, "24h": 86400e3, "7d": 7 * 86400e3 };
const OFF = { state: "off", id: null, created_at: null, expires_at: null, last_used_at: null, uses_approx: 0 };

export function createStub() {
  let key = { ...OFF };
  let failing = false;
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
          const ttl = JSON.parse(body || "{}").ttl ?? "24h";
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
