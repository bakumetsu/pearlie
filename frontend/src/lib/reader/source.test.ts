// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { komgaSource, webSource } from "./source";
import { getWebPage, setWebPage } from "./webProgress";
import type { Api } from "../api/client";

function memStorage() {
  const m = new Map<string, string>();
  return {
    getItem: (k: string) => (m.has(k) ? m.get(k)! : null),
    setItem: (k: string, v: string) => void m.set(k, String(v)),
    removeItem: (k: string) => void m.delete(k),
    clear: () => m.clear(),
  };
}

const KEY = "pearlie.webread.v1";

function book(over: Record<string, unknown> = {}) {
  return {
    title_main: "Main",
    title: "Full title",
    page_count: 20,
    page_url: "/api/media/web/nhentai/123/pages/{n}",
    page_thumb_url: "/api/media/web/nhentai/123/pages/{n}/thumb",
    item: { source: "nhentai", post_id: "123" },
    ...over,
  };
}

function fakeApi(over: Record<string, unknown> = {}): Api {
  return {
    webBook: vi.fn(async () => book()),
    getItem: vi.fn(async (kind: string, id: string) =>
      kind === "books"
        ? { title: "B" + id, page_count: 30, page_url: "/p/{n}", page_thumb_url: "/t/{n}", read_page: 12 }
        : { books: [{ id: "b1" }, { id: "b2" }], notice: { message: "hi" } },
    ),
    saveProgress: vi.fn(async () => ({})),
    ...over,
  } as unknown as Api;
}

beforeEach(() => vi.stubGlobal("localStorage", memStorage()));
afterEach(() => {
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("webSource", () => {
  it("loads the book from the web proxy with templates and no series", async () => {
    const api = fakeApi();
    const d = await webSource(api, "nhentai", "123", new URLSearchParams()).load();
    expect(api.webBook).toHaveBeenCalledWith("nhentai", "123");
    expect(d).toMatchObject({
      title: "Main",
      count: 20,
      tpl: "/api/media/web/nhentai/123/pages/{n}",
      thumbTpl: "/api/media/web/nhentai/123/pages/{n}/thumb",
      start: 1,
      books: [],
      notice: null,
    });
    expect(api.getItem).not.toHaveBeenCalled();
  });

  it("resumes from the saved page, ?p wins, edge pages start at 1", async () => {
    const api = fakeApi();
    setWebPage("nhentai:123", 7, 20);
    expect((await webSource(api, "nhentai", "123", new URLSearchParams()).load()).start).toBe(7);
    expect((await webSource(api, "nhentai", "123", new URLSearchParams("p=4")).load()).start).toBe(4);
    localStorage.setItem(KEY, JSON.stringify({ "nhentai:123": { page: 20, ts: 1 } }));
    expect((await webSource(api, "nhentai", "123", new URLSearchParams()).load()).start).toBe(1);
  });

  it("rejects a source other than nhentai", async () => {
    await expect(webSource(fakeApi(), "danbooru", "1", new URLSearchParams()).load()).rejects.toThrow();
  });

  it("saveProgress writes local storage only, never the API", () => {
    const api = fakeApi();
    const s = webSource(api, "nhentai", "123", new URLSearchParams());
    s.saveProgress(5, 20);
    expect(getWebPage("nhentai:123")).toBe(5);
    expect(api.saveProgress).not.toHaveBeenCalled();
  });

  it("back target is the discover page", () => {
    expect(webSource(fakeApi(), "nhentai", "1", new URLSearchParams()).backTarget()).toBe("/web/nhentai/1");
  });
});

describe("komgaSource", () => {
  it("loads book and series, applies the Komga resume rule", async () => {
    const api = fakeApi();
    const d = await komgaSource(api, "k1", new URLSearchParams("series=s9")).load();
    expect(d).toMatchObject({ title: "Bk1", count: 30, start: 12, notice: "hi" });
    expect(d.books).toHaveLength(2);
    expect(api.getItem).toHaveBeenCalledWith("series", "s9");
  });

  it("saves progress through the API and backs to the series", () => {
    const api = fakeApi();
    const s = komgaSource(api, "k1", new URLSearchParams("series=s9"));
    s.saveProgress(3, 30, { keepalive: true });
    expect(api.saveProgress).toHaveBeenCalledWith("k1", 3, undefined, { keepalive: true });
    expect(s.backTarget()).toBe("/item/series/s9");
    expect(komgaSource(api, "k1", new URLSearchParams()).backTarget()).toBe("/item/books/k1");
  });

  it("fetches book and series at the same time", async () => {
    const order: string[] = [];
    const api = fakeApi({
      getItem: vi.fn(async (kind: string) => {
        order.push(kind);
        await Promise.resolve();
        return kind === "series" ? { books: [] } : { title: "T", page_count: 5, page_url: "/p/{n}" };
      }),
    });
    const p = komgaSource(api, "k1", new URLSearchParams("series=s")).load();
    expect(order).toEqual(["books", "series"]);
    await p;
  });

  it("a failed book load rejects", async () => {
    const api = fakeApi({ getItem: vi.fn(async () => { throw new Error("x"); }) });
    await expect(komgaSource(api, "k1", new URLSearchParams()).load()).rejects.toThrow();
  });

  it("a failed series load keeps the book", async () => {
    const api = fakeApi({
      getItem: vi.fn(async (kind: string) => {
        if (kind === "series") throw new Error("x");
        return { title: "T", page_count: 5, page_url: "/p/{n}" };
      }),
    });
    const d = await komgaSource(api, "k1", new URLSearchParams("series=s")).load();
    expect(d.books).toEqual([]);
    expect(d.start).toBe(1);
  });
});

describe("webProgress", () => {
  it("page 1 and last page clear the entry", () => {
    setWebPage("nhentai:1", 5, 10);
    setWebPage("nhentai:1", 10, 10);
    expect(getWebPage("nhentai:1")).toBeNull();
    setWebPage("nhentai:1", 5, 10);
    setWebPage("nhentai:1", 1, 10);
    expect(getWebPage("nhentai:1")).toBeNull();
  });

  it("keeps at most 200 entries and drops the oldest", () => {
    for (let i = 0; i < 205; i++) setWebPage("nhentai:" + i, 2, 10, 1000 + i);
    const s = JSON.parse(localStorage.getItem(KEY)!);
    expect(Object.keys(s)).toHaveLength(200);
    expect(s["nhentai:0"]).toBeUndefined();
    expect(s["nhentai:204"]).toBeDefined();
  });

  it("survives broken storage and corrupt data", () => {
    localStorage.setItem(KEY, "{not json");
    expect(getWebPage("nhentai:1")).toBeNull();
    setWebPage("nhentai:1", 3, 10);
    expect(getWebPage("nhentai:1")).toBe(3);
    vi.spyOn(localStorage, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(localStorage, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(getWebPage("nhentai:1")).toBeNull();
    expect(() => setWebPage("nhentai:1", 4, 10)).not.toThrow();
  });
});
