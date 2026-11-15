// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, cleanup, fireEvent, waitFor } from "@testing-library/svelte";
import BookStage from "./BookStage.svelte";
import type { LibraryItemDetail } from "../api/client";

afterEach(cleanup);

function setup(over: Partial<LibraryItemDetail> = {}, saveProgress = vi.fn(async () => ({ page: 8, completed: true }))) {
  const detail = {
    kind: "book",
    id: "b1",
    title: "Komga Book",
    thumb_url: "/cover",
    page_count: 8,
    read_page: 3,
    page_thumb_url: "/api/media/komga/books/b1/pages/{n}/thumb",
    ...over,
  } as LibraryItemDetail;
  const onread = vi.fn();
  const onerror = vi.fn();
  const r = render(BookStage, { props: { detail, api: { saveProgress }, onread, onerror } });
  return { ...r, saveProgress, onread, onerror };
}

describe("BookStage", () => {
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

  it("marks the book read with the last page and disables the button", async () => {
    const { getByLabelText, saveProgress, container } = setup();
    await fireEvent.click(getByLabelText("Mark read"));
    expect(saveProgress).toHaveBeenCalledWith("b1", 8);
    await waitFor(() => expect((getByLabelText("Read") as HTMLButtonElement).disabled).toBe(true));
    expect(container.querySelector("button.thumb.last")).toBeNull();
  });

  it("reports an error when mark read fails", async () => {
    const { getByLabelText, onerror } = setup({}, vi.fn(async () => { throw new Error("x"); }));
    await fireEvent.click(getByLabelText("Mark read"));
    await waitFor(() => expect(onerror).toHaveBeenCalled());
  });

  it("has no Delete button until a hook is passed", () => {
    const { queryByLabelText } = setup();
    expect(queryByLabelText("Delete")).toBeNull();
  });
});
