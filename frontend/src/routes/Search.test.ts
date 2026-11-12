// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import App from "../App.svelte";

describe("Search chips do not auto-run", () => {
  let searchCalls: number;
  let lastBody: string;

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
    lastBody = "";
    globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(
        typeof input === "string" ? input : input instanceof URL ? input.href : input.url,
        "http://localhost",
      );
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

    await fireEvent.click(screen.getByRole("button", { name: "Remove dog" }));
    await settle();
    expect(searchCalls).toBe(base);
    expect(screen.queryByRole("button", { name: "Search" })).toBeNull();
  });

  it("blur only adds the chip", async () => {
    render(App);
    await settle();
    const base = searchCalls;
    const input = screen.getByRole("textbox");
    await fireEvent.input(input, { target: { value: "dog" } });
    await fireEvent.blur(input);
    await settle();
    expect(searchCalls).toBe(base);
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
});
