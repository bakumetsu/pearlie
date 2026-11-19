// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, cleanup, fireEvent, waitFor } from "@testing-library/svelte";
import StumpBook from "./StumpBook.svelte";
import type { LibraryItemDetail } from "../api/client";

vi.mock("../ctx", () => ({ getRouter: () => ({ navigate: vi.fn() }) }));

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
  const r = render(StumpBook, { props: { detail, api: { saveProgress }, tags: ["a"], ...fns, ...extra } });
  return { ...r, saveProgress, ...fns };
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

  it("has the 260 px column with rating and tags, and no panel handle", () => {
    const { getByText, queryByLabelText, container } = setup();
    expect(getByText("Rating")).toBeTruthy();
    expect(getByText("Tags")).toBeTruthy();
    expect(container.querySelector("aside.side")).toBeTruthy();
    expect(queryByLabelText("Hide panel")).toBeNull();
  });

  it("shows a note and no Read button for a book without pages", () => {
    const { getByText, queryByText } = setup({ page_count: 0 });
    expect(getByText("This book has no pages.")).toBeTruthy();
    expect(queryByText("Read")).toBeNull();
  });
});
