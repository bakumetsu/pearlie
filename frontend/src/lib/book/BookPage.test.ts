// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, cleanup, fireEvent } from "@testing-library/svelte";
import { createRawSnippet } from "svelte";
import css from "./BookPage.svelte?raw";
import BookPage from "./BookPage.svelte";

afterEach(cleanup);

const snip = (html: string) => createRawSnippet(() => ({ render: () => html }));

describe("BookPage", () => {
  it("shows the title, sub lines, backdrop and calls onback", async () => {
    const onback = vi.fn();
    const { container, getByText, getByLabelText } = render(BookPage, {
      props: { cover: "/c", backdrop: "/c", title: "Big", sub: ["Jp", "", "En"], by: "Someone", onback },
    });
    expect(getByText("Big")).toBeTruthy();
    expect(container.querySelectorAll(".sub")).toHaveLength(2);
    expect(getByText("Someone")).toBeTruthy();
    expect(container.querySelector(".backdrop")).toBeTruthy();
    await fireEvent.click(getByLabelText("Back"));
    expect(onback).toHaveBeenCalled();
  });

  it("hides the backdrop at strength 0 and the More button without actions", () => {
    const { container, queryByLabelText } = render(BookPage, {
      props: { cover: "/c", backdrop: "/c", backdropStrength: 0, title: "T", onback: () => {} },
    });
    expect(container.querySelector(".backdrop")).toBeNull();
    expect(queryByLabelText("More actions")).toBeNull();
  });

  it("opens the menu, closes it on an item click and on Escape", async () => {
    const { container, getByLabelText } = render(BookPage, {
      props: { cover: "/c", title: "T", onback: () => {}, actions: snip('<button class="mi" role="menuitem">Go</button>') },
    });
    const more = getByLabelText("More actions");
    await fireEvent.click(more);
    expect(container.querySelector(".menu")).toBeTruthy();
    await fireEvent.click(container.querySelector(".mi")!);
    expect(container.querySelector(".menu")).toBeNull();
    await fireEvent.click(more);
    await fireEvent.keyDown(window, { key: "Escape" });
    expect(container.querySelector(".menu")).toBeNull();
  });

  it("closes the menu on a pointer down outside it, not on the button or inside", async () => {
    const { container, getByLabelText } = render(BookPage, {
      props: { cover: "/c", title: "T", onback: () => {}, actions: snip('<button class="mi" role="menuitem">Go</button>') },
    });
    const more = getByLabelText("More actions");
    await fireEvent.click(more);
    expect(container.querySelector(".menu")).toBeTruthy();
    await fireEvent.pointerDown(container.querySelector(".menu")!);
    expect(container.querySelector(".menu")).toBeTruthy();
    await fireEvent.pointerDown(container.querySelector(".title")!);
    expect(container.querySelector(".menu")).toBeNull();
    await fireEvent.click(more);
    expect(container.querySelector(".menu")).toBeTruthy();
    await fireEvent.pointerDown(more);
    await fireEvent.click(more);
    expect(container.querySelector(".menu")).toBeNull();
  });

  it("renders only the bar and content when not ready", () => {
    const { container, getByText } = render(BookPage, {
      props: { ready: false, onback: () => {}, children: snip("<p>Loading…</p>") },
    });
    expect(getByText("Loading…")).toBeTruthy();
    expect(container.querySelector(".hero")).toBeNull();
  });
  it("keeps the tools at the right end of the hero row, with the More button at the left", () => {
    const { container } = render(BookPage, {
      props: { cover: "/c", title: "T", onback: () => {}, actions: snip('<button class="mi" role="menuitem">Go</button>'), tools: snip('<button class="tg">v</button>') },
    });
    const acts = container.querySelector(".acts")!;
    const tl = container.querySelector(".tl")!;
    expect(acts.children[0].getAttribute("aria-label")).toBe("More actions");
    expect(acts.lastElementChild).toBe(tl);
    // jsdom does not inject component CSS: assert on the source rules
    expect(css).toMatch(/\.acts[^{]*\{[^}]*align-self:\s*stretch/);
    expect(css).toMatch(/\.tl[^{]*\{[^}]*margin-left:\s*auto/);
  });
});
