// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import App from "../App.svelte";

describe("Search chips do not auto-run", () => {
  let searchCalls: number;
  let lastBody: string;
  let hiddenSites: string[] = [];

  beforeEach(() => {
    vi.stubGlobal("localStorage", {
      getItem: () => null,
      setItem: () => {},
      removeItem: () => {},
      clear: () => {},
    });
    vi.stubGlobal("IntersectionObserver", class { observe() {} disconnect() {} unobserve() {} });
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} unobserve() {} });
    window.scrollTo = vi.fn();
    history.replaceState({}, "", "/?q=cat");
    searchCalls = 0;
    hiddenSites = [];
    lastBody = "";
    globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(
        typeof input === "string" ? input : input instanceof URL ? input.href : input.url,
        "http://localhost",
      );
      if (url.pathname === "/api/options") {
        return Promise.resolve(
          new Response(JSON.stringify({ hidden_sites: hiddenSites }), {
            status: 200,
            headers: { "Content-Type": "application/json" },
          }),
        );
      }
      if (url.pathname === "/api/search") {
        searchCalls++;
        lastBody = url.search + String(init?.body ?? "");
      }
      return Promise.resolve(
        new Response(JSON.stringify({ sections: [] }), {
          status: 200,
          headers: { "Content-Type": "application/json" },
        }),
      );
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  async function settle() {
    await new Promise((r) => setTimeout(r, 450));
  }

  it("adding and removing a chip sends nothing; Search button shows when changed", async () => {
    render(App);
    await settle();
    const base = searchCalls;
    expect(base).toBe(1);
    expect(screen.queryByRole("button", { name: "Search" })).toBeNull();

    const input = screen.getByRole("textbox");
    await fireEvent.input(input, { target: { value: "dog" } });
    await fireEvent.keyDown(input, { key: "Enter" });
    await settle();
    expect(searchCalls).toBe(base);
    expect(screen.getByRole("button", { name: "Search" })).toBeTruthy();
    // The button sits inside the field, so the field keeps its width.
    expect(screen.getByRole("button", { name: "Search" }).closest(".field")).not.toBeNull();

    await fireEvent.click(screen.getByRole("button", { name: "Remove dog" }));
    await settle();
    expect(searchCalls).toBe(base);
    expect(screen.queryByRole("button", { name: "Search" })).toBeNull();
  });

  it("blur keeps the text uncommitted and shows Search", async () => {
    render(App);
    await settle();
    const base = searchCalls;
    const input = screen.getByRole("textbox") as HTMLInputElement;
    await fireEvent.input(input, { target: { value: "dog" } });
    await fireEvent.blur(input);
    await settle();
    expect(searchCalls).toBe(base);
    expect(screen.queryByRole("button", { name: "Remove dog" })).toBeNull();
    expect(input.value).toBe("dog");
    expect(screen.getByRole("button", { name: "Search" })).toBeTruthy();
  });

  it("Search button commits pending text and runs once", async () => {
    render(App);
    await settle();
    const base = searchCalls;
    const input = screen.getByRole("textbox") as HTMLInputElement;
    await fireEvent.input(input, { target: { value: "dog" } });
    await fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await settle();
    expect(searchCalls).toBe(base + 1);
    expect(lastBody).toContain("dog");
    expect(input.value).toBe("");
    expect(screen.getByRole("button", { name: "Remove dog" })).toBeTruthy();
  });

  it("Enter on an empty field runs once, then an identical query is not re-sent", async () => {
    render(App);
    await settle();
    const base = searchCalls;
    const input = screen.getByRole("textbox");
    await fireEvent.input(input, { target: { value: "dog" } });
    await fireEvent.keyDown(input, { key: "Enter" });
    await fireEvent.keyDown(input, { key: "Enter" });
    await settle();
    expect(searchCalls).toBe(base + 1);
    expect(lastBody).toContain("dog");
    await fireEvent.keyDown(input, { key: "Enter" });
    await settle();
    expect(searchCalls).toBe(base + 1);
    expect(screen.queryByRole("button", { name: "Search" })).toBeNull();
  });

  it("removing a filter chip keeps hidden sites, draft chips and pending text", async () => {
    hiddenSites = ["rule34"];
    history.replaceState({}, "", "/?q=cat&sites=danbooru,gelbooru,rule34");
    render(App);
    await settle();
    const input = screen.getByRole("textbox") as HTMLInputElement;
    await fireEvent.input(input, { target: { value: "dog" } });
    await fireEvent.keyDown(input, { key: "Enter" });
    await fireEvent.input(input, { target: { value: "bird" } });
    await fireEvent.click(screen.getByRole("button", { name: "Remove Gelbooru" }));
    await settle();
    const params = new URLSearchParams(location.search);
    expect(params.get("sites")).toBe("danbooru,rule34");
    expect(params.get("q") ?? "").not.toContain("dog");
    expect(screen.getByRole("button", { name: "Remove dog" })).toBeTruthy();
    expect(input.value).toBe("bird");
  });
});
