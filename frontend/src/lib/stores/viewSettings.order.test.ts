import { describe, it, expect, vi } from "vitest";
import type { Api } from "../api/client";
import { createViewSettings } from "./viewSettings.svelte";

type Body = { mode: string; per_page: number; zoom: number };
const reply = (b: Body) => ({ ...b, per_page_options: [60], per_page_max: 200, modes: ["grid", "wall", "masonry", "list"] });

describe("viewSettings out-of-order PUTs", () => {
  it("a slow older PUT response never overwrites a newer value", async () => {
    const resolvers: Array<() => void> = [];
    const bodies: Body[] = [];
    const api = {
      getViewSettings: vi.fn().mockResolvedValue({ sources: {} }),
      putViewSetting: vi.fn().mockImplementation((_s: string, body: Body) => {
        bodies.push(body);
        return new Promise((res) => resolvers.push(() => res(reply(body))));
      }),
    } as unknown as Api;
    const store = createViewSettings();
    await store.load(api);

    const first = store.set("danbooru", { zoom: 2 });
    const second = store.set("danbooru", { zoom: 5 });
    // let every queued PUT go out, newest answering first
    for (let i = 0; i < 10 && resolvers.length < 2; i++) {
      resolvers.slice().reverse().forEach((r) => r());
      await Promise.resolve();
    }
    resolvers.slice().reverse().forEach((r) => r());
    await Promise.all([first, second]);

    expect(store.sources.danbooru.zoom).toBe(5);
    expect(bodies[bodies.length - 1].zoom).toBe(5);
  });
});
