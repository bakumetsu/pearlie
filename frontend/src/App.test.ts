// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup } from "@testing-library/svelte";
import App from "./App.svelte";

beforeEach(() => {
  history.replaceState({}, "", "/");
  globalThis.fetch = vi.fn().mockImplementation(() =>
    Promise.resolve(
      new Response(JSON.stringify({ query: "", sections: [] }), {
        status: 200,
        headers: { "Content-Type": "application/json" },
      }),
    ),
  );
});

afterEach(() => {
  cleanup();
});

describe("App shell", () => {
  it("renders the main navigation with links named Discover, Library, Queue, Options", () => {
    render(App);

    const nav = screen.getByRole("navigation", { name: "Main" });
    const links = nav.querySelectorAll("a");
    const names = Array.from(links).map((a) => a.textContent?.trim());

    expect(names).toContain("Discover");
    expect(names).toContain("Home");
    expect(names).toContain("Library");
    expect(names).toContain("Queue");
    expect(names).not.toContain("Rules");
    expect(names).toContain("Options");
    expect(names[names.length - 1]).toBe("Options");
    expect(names[names.length - 2]).toBe("Trash");
  });

  it('marks the "Library" link with aria-current="page" at /library', () => {
    history.replaceState({}, "", "/library");
    render(App);

    const libLink = screen.getByRole("link", { name: "Library" });
    expect(libLink.getAttribute("aria-current")).toBe("page");
  });

  it('shows the "Queue" heading at /queue', () => {
    history.replaceState({}, "", "/queue");
    render(App);

    expect(screen.getByRole("heading", { name: "Queue" })).toBeTruthy();
  });

  it('shows the "Home" heading at /home', () => {
    history.replaceState({}, "", "/home");
    render(App);

    expect(screen.getByRole("heading", { name: "Home" })).toBeTruthy();
  });

  it('shows the default section heading at /options', () => {
    history.replaceState({}, "", "/options");
    render(App);

    expect(screen.getByRole("heading", { name: "General" })).toBeTruthy();
  });

  it("redirects /option to /options", () => {
    history.replaceState({}, "", "/option");
    render(App);

    expect(window.location.pathname).toBe("/options");
  });

  it("redirects /rules to /options/rules", () => {
    history.replaceState({}, "", "/rules");
    render(App);

    expect(window.location.pathname).toBe("/options/rules");
  });
});
