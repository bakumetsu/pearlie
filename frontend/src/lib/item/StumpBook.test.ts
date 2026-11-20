// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, cleanup, fireEvent, waitFor } from "@testing-library/svelte";
import StumpBook from "./StumpBook.svelte";
import { API_CONTEXT_KEY } from "../api/client";
import type { Api, LibraryItemDetail } from "../api/client";

const navigate = vi.hoisted(() => vi.fn());
vi.mock("../ctx", () => ({ getRouter: () => ({ navigate }) }));

afterEach(cleanup);

function setup(over: Partial<LibraryItemDetail> = {}, saveProgress = vi.fn(async () => ({ page: 8, completed: true })), extra: Record<string, unknown> = {}) {
  const detail = {
    kind: "book",
    id: "b1",
    title: "Stump Book",
    thumb_url: "/cover",
    page_count: 8,
    read_page: 3,
    favorite: false,
    added_at: "2026-01-01T00:00:00Z",
    page_thumb_url: "/api/media/stump/books/b1/pages/{n}/thumb",
    ...over,
  } as LibraryItemDetail;
  const fns = {
    onback: vi.fn(), onread: vi.fn(), onerror: vi.fn(), onfavorite: vi.fn(), ondelete: vi.fn(),
    onrate: vi.fn(), onaddtag: vi.fn(), onremovetag: vi.fn(),
  };
  const panelApi = {
    recommend: vi.fn(async () => ({ items: [{ kind: "book", id: "r1", title: "Rec One", thumb_url: "/r1" }] })),
    recommendRandom: vi.fn(async () => ({ items: [] })),
  };
  const context = new Map<unknown, unknown>([[API_CONTEXT_KEY, panelApi as unknown as Api]]);
  const r = render(StumpBook, { props: { detail, api: { saveProgress }, tags: ["a"], ...fns, ...extra }, context });
  return { ...r, saveProgress, panelApi, ...fns };
}

async function openMenu(r: ReturnType<typeof setup>) {
  await fireEvent.click(r.getByLabelText("More actions"));
}

describe("StumpBook", () => {
  it("shows Continue, all page thumbnails and the last-read outline", () => {
    const { container, getByText } = setup();
    expect(getByText("Continue")).toBeTruthy();
    expect(container.querySelectorAll("button.thumb").length).toBe(8);
    expect(container.querySelector("button.thumb.last")?.getAttribute("aria-label")).toBe("Page 3");
  });

  it("shows Read for an unread book and opens the reader without a page", async () => {
    const { getByText, onread } = setup({ read_page: null });
    await fireEvent.click(getByText("Read"));
    expect(onread).toHaveBeenCalledWith();
  });

  it("opens the reader at the tapped page", async () => {
    const { getByLabelText, onread } = setup();
    await fireEvent.click(getByLabelText("Page 5"));
    expect(onread).toHaveBeenCalledWith(5);
  });

  it("marks the book read from the menu and drops the outline", async () => {
    const r = setup();
    await openMenu(r);
    await fireEvent.click(r.getByText("Mark read"));
    expect(r.saveProgress).toHaveBeenCalledWith("b1", 8);
    await waitFor(() => expect(r.container.querySelector("button.thumb.last")).toBeNull());
  });

  it("reports an error when mark read fails", async () => {
    const r = setup({}, vi.fn(async () => { throw new Error("x"); }));
    await openMenu(r);
    await fireEvent.click(r.getByText("Mark read"));
    await waitFor(() => expect(r.onerror).toHaveBeenCalled());
  });

  it("menu favorite and delete call the handlers", async () => {
    const r = setup();
    await openMenu(r);
    await fireEvent.click(r.getByText("Favorite"));
    expect(r.onfavorite).toHaveBeenCalled();
    await openMenu(r);
    await fireEvent.click(r.getByText("Delete"));
    expect(r.ondelete).toHaveBeenCalled();
  });

  it("prev and next buttons show only for list items and call the handlers", async () => {
    const none = setup();
    expect(none.queryByLabelText("Next item")).toBeNull();
    cleanup();
    const onprev = vi.fn();
    const onnext = vi.fn();
    const r = setup({}, undefined, { onprev, onnext, canPrev: true, canNext: true });
    await fireEvent.click(r.getByLabelText("Next item"));
    await fireEvent.click(r.getByLabelText("Previous item"));
    expect(onnext).toHaveBeenCalled();
    expect(onprev).toHaveBeenCalled();
  });

  it("shows the rating under the author, tag chips and no Rating or Details section", () => {
    const { getByRole, getByText, queryByText, queryByLabelText } = setup({ author: "Some Author" });
    expect(getByText("Some Author")).toBeTruthy();
    expect(getByRole("radiogroup", { name: "Rating" })).toBeTruthy();
    expect(getByText("Tags")).toBeTruthy();
    expect(getByText("a")).toBeTruthy();
    expect(queryByText("Rating")).toBeNull();
    expect(queryByText("Details")).toBeNull();
    expect(queryByLabelText("Hide panel")).toBeNull();
  });

  it("asks for Stump recommendations and random with limit 4", async () => {
    const r = setup();
    await waitFor(() => expect(r.panelApi.recommend).toHaveBeenCalledWith({ source: "stump", id: "b1", kind: "book", limit: 6 }));
    expect(r.panelApi.recommendRandom).toHaveBeenCalledWith({ source: "stump", limit: 4, exclude: "b1" });
  });

  it("opens a recommendation on the Stump page, not /web/", async () => {
    const r = setup();
    await fireEvent.click(await r.findByText("Rec One"));
    expect(navigate).toHaveBeenCalledWith("/item/books/r1");
  });

  it("rejects a tag from the menu picker", async () => {
    const onrejecttag = vi.fn();
    const r = setup({}, undefined, { onrejecttag });
    await openMenu(r);
    await fireEvent.click(r.getByText("Reject a tag"));
    await fireEvent.click(r.getByRole("group", { name: "Reject a tag" }).querySelector("button")!);
    expect(onrejecttag).toHaveBeenCalledWith("a");
  });

  it("has no Reject menu item without a handler", async () => {
    const r = setup();
    await openMenu(r);
    expect(r.queryByText("Reject a tag")).toBeNull();
  });

  it("shows a note and no Read button for a book without pages", () => {
    const { getByText, queryByText } = setup({ page_count: 0 });
    expect(getByText("This book has no pages.")).toBeTruthy();
    expect(queryByText("Read")).toBeNull();
  });
});
