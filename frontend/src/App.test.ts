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
  it("renders the main navigation with links named Discover, Library, Queue, Rules", () => {
    render(App);

    const nav = screen.getByRole("navigation", { name: "Main" });
    const links = nav.querySelectorAll("a");
    const names = Array.from(links).map((a) => a.textContent?.trim());

    expect(names).toContain("Discover");
    expect(names).toContain("Home");
    expect(names).toContain("Library");
    expect(names).toContain("Queue");
    expect(names).toContain("Rules");
    expect(names).toContain("Option");
    expect(names[names.length - 1]).toBe("Option");
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

  it('shows the "Option" heading at /option', () => {
    history.replaceState({}, "", "/option");
    render(App);

    expect(screen.getByRole("heading", { name: "Option" })).toBeTruthy();
  });
});
