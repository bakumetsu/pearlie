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
});
