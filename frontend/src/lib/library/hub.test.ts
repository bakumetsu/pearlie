import { describe, it, expect, vi } from "vitest";
import { HUBS, HUB_KEY, isHub, loadHub, saveHub, hubKinds } from "./hub";
import type { Kind } from "../api/client";

function fakeStorage(data: Record<string, string> = {}) {
  const store = new Map(Object.entries(data));
  return {
    getItem: vi.fn((key: string) => store.get(key) ?? null),
    setItem: vi.fn((key: string, value: string) => {
      store.set(key, value);
    }),
  };
}

describe("loadHub", () => {
  it("defaults to \"all\" when storage is empty", () => {
    const storage = fakeStorage();
    expect(loadHub(storage)).toBe("all");
  });

  it("defaults to \"all\" when stored value is invalid", () => {
    const storage = fakeStorage({ [HUB_KEY]: "bogus" });
    expect(loadHub(storage)).toBe("all");
  });

  it("defaults to \"all\" when getItem throws", () => {
    const storage = { getItem: vi.fn(() => { throw new Error("denied"); }) };
    expect(loadHub(storage)).toBe("all");
  });

  it("returns stored value when valid", () => {
    const storage = fakeStorage({ [HUB_KEY]: "komga" });
    expect(loadHub(storage)).toBe("komga");
  });
});

describe("saveHub", () => {
  it("writes the key", () => {
    const storage = fakeStorage();
    saveHub("stash", storage);
    expect(storage.setItem).toHaveBeenCalledWith(HUB_KEY, "stash");
  });

  it("does not throw when setItem throws", () => {
    const storage = { setItem: vi.fn(() => { throw new Error("quota"); }) };
    expect(() => saveHub("all", storage)).not.toThrow();
  });
});

describe("hubKinds", () => {
  const all: Kind[] = ["images", "videos", "series", "books"];

  it("filters stash to images and videos", () => {
    expect(hubKinds("stash", all)).toEqual(["images", "videos"]);
  });

  it("returns all four for \"all\"", () => {
    expect(hubKinds("all", all)).toEqual(["images", "videos", "series", "books"]);
  });
});

describe("HUBS", () => {
  it("every id satisfies isHub", () => {
    for (const h of HUBS) {
      expect(isHub(h.id)).toBe(true);
    }
  });
});
