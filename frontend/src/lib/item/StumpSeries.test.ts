// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, cleanup, fireEvent, waitFor } from "@testing-library/svelte";
import StumpSeries from "./StumpSeries.svelte";
import { API_CONTEXT_KEY } from "../api/client";
import type { Api, LibraryItem, LibraryItemDetail } from "../api/client";

vi.mock("../ctx", () => ({ getRouter: () => ({ navigate: vi.fn() }) }));

const store = new Map<string, string>();
vi.stubGlobal("localStorage", {
  getItem: (k: string) => store.get(k) ?? null,
  setItem: (k: string, v: string) => void store.set(k, v),
});

afterEach(() => {
  cleanup();
  store.clear();
});

const book = (id: string, read_page?: number, page_count = 10) =>
  ({ kind: "book", id, title: "Book " + id, thumb_url: "/t/" + id, read_page, page_count }) as LibraryItem;

function setup(over: Partial<LibraryItemDetail> = {}, extra: Record<string, unknown> = {}) {
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
    inherited_tags: [{ name: "seinen" }],
    studio: "Studio",
    ...over,
  } as unknown as LibraryItemDetail;
  const fns = {
    onback: vi.fn(), onopen: vi.fn(), onfavorite: vi.fn(), ondelete: vi.fn(),
    onrate: vi.fn(), onaddtag: vi.fn(), onremovetag: vi.fn(),
  };
  const panelApi = { recommend: vi.fn(async () => ({ items: [] })), recommendRandom: vi.fn(async () => ({ items: [] })) };
  const context = new Map<unknown, unknown>([[API_CONTEXT_KEY, panelApi as unknown as Api]]);
  const r = render(StumpSeries, { props: { detail, tags: ["action"], ...fns, ...extra }, context });
  return { ...r, panelApi, ...fns };
}

describe("StumpSeries", () => {
  it("Continue opens the first unfinished book", async () => {
    const { getByText, onopen } = setup();
    await fireEvent.click(getByText("Continue"));
    expect(onopen.mock.calls[0][0].id).toBe("b2");
  });

  it("shows Read and opens book 1 when nothing was read", async () => {
    const { getByText, onopen } = setup({ read_count: 0, books: [book("b1"), book("b2")] });
    await fireEvent.click(getByText("Read"));
    expect(onopen.mock.calls[0][0].id).toBe("b1");
  });

  it("marks tiles: check on finished, outline on the Continue book, bar on progress", () => {
    const { container, getByLabelText } = setup();
    expect(getByLabelText("Book b1, read").querySelector(".tick")).toBeTruthy();
    expect(container.querySelectorAll("button.tile.cont").length).toBe(1);
    expect(container.querySelector("button.tile.cont")?.getAttribute("aria-label")).toBe("Book b2");
    expect(container.querySelectorAll(".tile .pb").length).toBe(1);
  });

  it("hides the primary button and shows No books for an empty series", () => {
    const { queryByText, getByText } = setup({ books: [], book_count: 0 });
    expect(queryByText("Read")).toBeNull();
    expect(getByText("No books")).toBeTruthy();
  });

  it("shows the rating under the by-line and no progress bar or sub line", () => {
    const { container, getByRole, getByText } = setup({ author: "Some Author" });
    expect(getByText("Some Author")).toBeTruthy();
    expect(getByRole("radiogroup", { name: "Rating" })).toBeTruthy();
    expect(container.querySelector(".ratio")).toBeNull();
    expect(container.querySelector(".sub")).toBeNull();
  });

  it("shows own tags and a lock chip for a tag inherited from the books", () => {
    const { container, getByText } = setup();
    expect(getByText("action")).toBeTruthy();
    expect(container.querySelectorAll(".chip.locked").length).toBe(1);
    expect(container.querySelector(".chip.locked")?.textContent).toContain("seinen");
  });

  it("asks for series recommendations and random with limit 4", async () => {
    const r = setup();
    await waitFor(() => expect(r.panelApi.recommend).toHaveBeenCalledWith({ source: "stump", id: "s1", kind: "series", limit: 6 }));
    expect(r.panelApi.recommendRandom).toHaveBeenCalledWith({ source: "stump", limit: 4, exclude: "s1" });
  });

  it("toggles grid and list and remembers the choice", async () => {
    const r = setup();
    expect(r.container.querySelector(".grid")).toBeTruthy();
    await fireEvent.click(r.getByLabelText("Switch to list view"));
    expect(r.container.querySelector(".lv")).toBeTruthy();
    expect(r.container.querySelectorAll("button.row").length).toBe(3);
    expect(localStorage.getItem("pearlie.series.view")).toBe("list");
    cleanup();
    const again = setup();
    expect(again.container.querySelector(".lv")).toBeTruthy();
    expect(again.getByLabelText("Switch to grid view")).toBeTruthy();
  });

  it("offers Reject a tag only with a handler and calls it", async () => {
    const none = setup();
    await fireEvent.click(none.getByLabelText("More actions"));
    expect(none.queryByText("Reject a tag")).toBeNull();
    cleanup();
    const onrejecttag = vi.fn();
    const r = setup({}, { onrejecttag });
    await fireEvent.click(r.getByLabelText("More actions"));
    await fireEvent.click(r.getByText("Reject a tag"));
    await fireEvent.click(r.getByRole("group", { name: "Reject a tag" }).querySelector("button")!);
    expect(onrejecttag).toHaveBeenCalledWith("action");
  });

  it("a half-read book alone gives Continue on that book", async () => {
    const { getByText, onopen, container } = setup({ read_count: 0, books: [book("b1", 4), book("b2")] });
    expect(container.querySelector("button.tile.cont")?.getAttribute("aria-label")).toBe("Book b1");
    await fireEvent.click(getByText("Continue"));
    expect(onopen.mock.calls[0][0].id).toBe("b1");
  });

  it("nothing read: Read button and no outline", () => {
    const { getByText, container } = setup({ read_count: 0, books: [book("b1"), book("b2")] });
    expect(getByText("Read")).toBeTruthy();
    expect(container.querySelector("button.tile.cont")).toBeNull();
  });
});
