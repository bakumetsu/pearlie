// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, cleanup, fireEvent } from "@testing-library/svelte";
import KomgaSeries from "./KomgaSeries.svelte";
import type { LibraryItem, LibraryItemDetail } from "../api/client";

afterEach(cleanup);

const book = (id: string, read_page?: number, page_count = 10) =>
  ({ kind: "book", id, title: "Book " + id, thumb_url: "/t/" + id, read_page, page_count }) as LibraryItem;

function setup(over: Partial<LibraryItemDetail> = {}) {
  const books = [book("b1", 10), book("b2", 4), book("b3")];
  const detail = {
    kind: "series",
    id: "s1",
    title: "Series",
    thumb_url: "/cover",
    added_at: "2026-01-01T00:00:00Z",
    book_count: 3,
    read_count: 1,
    books,
    tags: [{ name: "action" }, { name: "seinen" }, { name: "third" }],
    studio: "Studio",
    ...over,
  } as unknown as LibraryItemDetail;
  const fns = {
    onback: vi.fn(), onopen: vi.fn(), onfavorite: vi.fn(), ondelete: vi.fn(),
    onrate: vi.fn(), onaddtag: vi.fn(), onremovetag: vi.fn(),
  };
  const r = render(KomgaSeries, { props: { detail, tags: ["action"], ...fns } });
  return { ...r, ...fns };
}

describe("KomgaSeries", () => {
  it("Continue opens the first unfinished book", async () => {
    const { getByText, onopen } = setup();
    await fireEvent.click(getByText("Continue"));
    expect(onopen.mock.calls[0][0].id).toBe("b2");
  });

  it("shows Read and opens book 1 when nothing was read", async () => {
    const { getByText, onopen } = setup({ read_count: 0 });
    await fireEvent.click(getByText("Read"));
    expect(onopen.mock.calls[0][0].id).toBe("b1");
  });

  it("marks tiles: check on finished, outline on the Continue book, bar on progress", () => {
    const { container, getByLabelText } = setup();
    expect(getByLabelText("Book b1, read").querySelector(".tick")).toBeTruthy();
    expect(container.querySelectorAll("button.tile.cont").length).toBe(1);
    expect(container.querySelector("button.tile.cont")?.getAttribute("aria-label")).toBe("Book b2");
    expect(container.querySelectorAll(".tile .bar").length).toBe(2);
  });

  it("hides the primary button and shows No books for an empty series", () => {
    const { queryByText, getByText } = setup({ books: [], book_count: 0 });
    expect(queryByText("Read")).toBeNull();
    expect(getByText("No books")).toBeTruthy();
  });

  it("shows two tag chips plus the studio and the series bar", () => {
    const { container } = setup();
    const subs = [...container.querySelectorAll(".sub")].map((e) => e.textContent);
    expect(subs).toEqual(["action", "seinen", "Studio"]);
    expect(container.querySelector(".ratio i")?.getAttribute("style")).toContain("33%");
  });
});
