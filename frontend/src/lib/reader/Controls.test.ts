import { render, cleanup } from "@testing-library/svelte";
import { describe, it, expect, vi, afterEach } from "vitest";

import Controls from "./Controls.svelte";

afterEach(cleanup);

vi.stubGlobal(
  "ResizeObserver",
  class {
    observe() {}
    unobserve() {}
    disconnect() {}
  },
);

function props(over: { total: number; hasSeries: boolean }) {
  const fn = vi.fn();
  return {
    hidden: false,
    popover: null,
    thumbsOpen: false,
    fullscreen: false,
    mode: "paged",
    fit: "width",
    dir: "ltr",
    zoom: 1,
    count: 10,
    shown: [1],
    thumbTpl: null,
    title: "Book",
    index: 1,
    books: [],
    bookId: "1",
    notice: null,
    onback: fn,
    onsettings: fn,
    onfit: fn,
    onmode: fn,
    onfullscreen: fn,
    onhelp: fn,
    onprev: fn,
    onnext: fn,
    onlist: fn,
    onjump: fn,
    onthumbs: fn,
    onzoomin: fn,
    onzoomout: fn,
    onzoomreset: fn,
    onsetmode: fn,
    onsetfit: fn,
    onsetdir: fn,
    onpick: fn,
    onclosepopover: fn,
    onhover: fn,
    onfocus: fn,
    ...over,
  } as never;
}

describe("Controls book pill", () => {
  it("is hidden for a oneshot (one book)", () => {
    const { queryByTestId } = render(Controls, props({ total: 1, hasSeries: true }));
    expect(queryByTestId("book-pill")).toBeNull();
  });

  it("is hidden for a book with no series", () => {
    const { queryByTestId } = render(Controls, props({ total: 0, hasSeries: false }));
    expect(queryByTestId("book-pill")).toBeNull();
  });

  it("is shown for a series with 2+ books", () => {
    const { queryByTestId } = render(Controls, props({ total: 2, hasSeries: true }));
    expect(queryByTestId("book-pill")).not.toBeNull();
  });
});
