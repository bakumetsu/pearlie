// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, cleanup, fireEvent, screen } from "@testing-library/svelte";
import App from "../App.svelte";

describe("Discover book id search", () => {
  beforeEach(() => {
    vi.stubGlobal("localStorage", { getItem: () => null, setItem: () => {}, removeItem: () => {}, clear: () => {} });
    vi.stubGlobal("IntersectionObserver", class { observe() {} disconnect() {} unobserve() {} });
    vi.stubGlobal("ResizeObserver", class { observe() {} disconnect() {} unobserve() {} });
    window.scrollTo = vi.fn();
    globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo | URL) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, "http://localhost");
      const body = url.pathname === "/api/search" ? { sections: [] } : {};
      return Promise.resolve(new Response(JSON.stringify(body), { status: 200, headers: { "Content-Type": "application/json" } }));
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  async function typeAndEnterless(text: string) {
    history.replaceState({}, "", "/");
    render(App);
    const input = (await screen.findAllByRole("textbox"))[0] as HTMLInputElement;
    await fireEvent.input(input, { target: { value: text } });
    return input;
  }

  async function typeAndEnter(text: string) {
    history.replaceState({}, "", "/");
    render(App);
    const input = (await screen.findAllByRole("textbox"))[0] as HTMLInputElement;
    await fireEvent.input(input, { target: { value: text } });
    await fireEvent.keyDown(input, { key: "Enter" });
    return input;
  }

  it("a plain number opens the nhentai book page", async () => {
    await typeAndEnter("177013");
    await vi.waitFor(() => expect(location.pathname).toBe("/web/nhentai/177013"));
  });

  it("an id: chip opens the nhentai book page", async () => {
    await typeAndEnter("id:177013");
    await vi.waitFor(() => expect(location.pathname).toBe("/web/nhentai/177013"));
  });

  it("other text stays a normal chip", async () => {
    const input = await typeAndEnter("cat");
    await new Promise((r) => setTimeout(r, 30));
    expect(location.pathname).toBe("/");
    expect(input.value).toBe("");
  });

  it("a number after another chip stays a chip", async () => {
    const input = await typeAndEnter("cat");
    await fireEvent.input(input, { target: { value: "177013" } });
    await fireEvent.keyDown(input, { key: "Enter" });
    await new Promise((r) => setTimeout(r, 30));
    expect(location.pathname).toBe("/");
  });

  it("the search button with a typed id opens the book page", async () => {
    const input = await typeAndEnterless("177013");
    expect(input.value).toBe("177013");
    await fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await vi.waitFor(() => expect(location.pathname).toBe("/web/nhentai/177013"));
  });

  it("one committed id chip then the search button opens the book page", async () => {
    const input = await typeAndEnterless("id:42");
    await fireEvent.keyDown(input, { key: "," });
    expect(location.pathname).toBe("/");
    await fireEvent.click(screen.getByRole("button", { name: "Search" }));
    await vi.waitFor(() => expect(location.pathname).toBe("/web/nhentai/42"));
  });

  it("a comma commits the id as a chip and does not navigate", async () => {
    const input = await typeAndEnterless("177013");
    await fireEvent.keyDown(input, { key: "," });
    await new Promise((r) => setTimeout(r, 30));
    expect(location.pathname).toBe("/");
    expect(input.value).toBe("");
  });
});
