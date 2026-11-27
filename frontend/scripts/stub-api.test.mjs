/* global fetch */
// @vitest-environment node
import { afterAll, beforeAll, describe, expect, it } from "vitest";
import { createStub } from "./stub-api.mjs";

describe("stub api", () => {
  const server = createStub();
  let base = "";
  beforeAll(async () => {
    await new Promise((ok) => server.listen(0, "127.0.0.1", ok));
    base = `http://127.0.0.1:${server.address().port}`;
  });
  afterAll(() => server.close());

  it("answers /__error with a real 500 and keeps serving; the next DELETE works", async () => {
    expect((await fetch(`${base}/__error`)).status).toBe(500);
    expect((await fetch(`${base}/api/options/debug-key`)).status).toBe(500);
    expect((await fetch(`${base}/api/options/debug-key`, { method: "DELETE" })).status).toBe(204);
    const after = await fetch(`${base}/api/options/debug-key`);
    expect(after.status).toBe(200);
    expect((await after.json()).state).toBe("off");
  });

  it("answers a bad POST body with 400 and stays alive", async () => {
    const bad = await fetch(`${base}/api/options/debug-key`, { method: "POST", body: "{nope" });
    expect(bad.status).toBe(400);
    expect((await fetch(`${base}/api/options/debug-key`)).status).toBe(200);
  });
  it("serves the merged row: ok, partial and slow (late Rule34 on the poll)", async () => {
    const get = async (q = "") => (await fetch(`${base}/api/discover/merged${q}`)).json();
    await fetch(`${base}/__merged?mode=ok`);
    const ok = await get();
    expect(ok.items).toHaveLength(48);
    expect(ok.items.slice(0, 4).map((i) => i.source)).toEqual(["danbooru", "gelbooru", "rule34", "nhentai"]);
    await fetch(`${base}/__merged?mode=partial`);
    const partial = await get();
    expect(partial.items.some((i) => i.source === "gelbooru")).toBe(false);
    expect(partial.sites.find((s) => s.id === "gelbooru").state).toBe("error");
    await fetch(`${base}/__merged?mode=slow`);
    expect((await get()).pending).toBe(true);
    const poll = await get("?have=danbooru,gelbooru,nhentai");
    expect(poll.pending).toBe(false);
    expect(poll.items.slice(0, 3).map((i) => i.source)).toEqual(["danbooru", "gelbooru", "nhentai"]);
  });

  it("serves the merged list pages with next_page null at the end", async () => {
    const p3 = await (await fetch(`${base}/api/discover/merged/list?page=3`)).json();
    expect(p3.next_page).toBeNull();
    expect(p3.items).toHaveLength(48);
  });
});
