import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/svelte";
import TagChips from "./TagChips.svelte";
import TagEditor from "./TagEditor.svelte";
import { tagSearchHref } from "../query";

const names = (n: number) => Array.from({ length: n }, (_, i) => ({ name: `tag${i}` }));

describe("TagChips", () => {
  afterEach(cleanup);

  it("tap searches the tag; x reports it with the mode label", async () => {
    const onsearch = vi.fn();
    const onx = vi.fn();
    render(TagChips, { tags: [{ name: "cat" }], mode: "reject", onsearch, onx });
    await fireEvent.click(screen.getByText("cat"));
    await fireEvent.click(screen.getByLabelText("Reject cat"));
    expect(onsearch).toHaveBeenCalledWith("cat");
    expect(onx).toHaveBeenCalledWith("cat", false);
  });

  it("uses Remove label in remove mode", () => {
    render(TagChips, { tags: [{ name: "cat" }], mode: "remove" });
    expect(screen.getByLabelText("Remove cat")).toBeTruthy();
  });

  it("rejected chip is struck through, tap is off, x undoes", async () => {
    const onsearch = vi.fn();
    const onx = vi.fn();
    render(TagChips, { tags: [{ name: "cat", state: "rejected" }], mode: "reject", onsearch, onx });
    await fireEvent.click(screen.getByText("cat"));
    expect(onsearch).not.toHaveBeenCalled();
    await fireEvent.click(screen.getByLabelText("Undo reject cat"));
    expect(onx).toHaveBeenCalledWith("cat", true);
  });

  it("inherited chip has no x, shows once when also own, own first", () => {
    render(TagChips, { tags: [{ name: "a" }], inherited: [{ name: "a" }, { name: "b" }] });
    expect(screen.getAllByText("a")).toHaveLength(1);
    expect(screen.queryByLabelText("Remove b")).toBeNull();
    expect(screen.getByTitle("From a book in this series. Change it on the book.")).toBeTruthy();
  });

  it("folds after 8 and expands and folds again", async () => {
    render(TagChips, { tags: names(10) });
    expect(screen.queryByText("tag8")).toBeNull();
    await fireEvent.click(screen.getByText("2 more"));
    expect(screen.getByText("tag9")).toBeTruthy();
    await fireEvent.click(screen.getByText("Show less"));
    expect(screen.queryByText("tag9")).toBeNull();
  });

  it("+ opens the input; Enter adds, Esc cancels, readonly hides +", async () => {
    const onadd = vi.fn();
    const { unmount } = render(TagChips, { tags: [], onadd });
    await fireEvent.click(screen.getByLabelText("Add tag"));
    let input = screen.getByPlaceholderText("Add tag");
    await fireEvent.input(input, { target: { value: " dog " } });
    await fireEvent.keyDown(input, { key: "Enter" });
    expect(onadd).toHaveBeenCalledWith("dog");
    await fireEvent.click(screen.getByLabelText("Add tag"));
    input = screen.getByPlaceholderText("Add tag");
    await fireEvent.keyDown(input, { key: "Escape" });
    expect(onadd).toHaveBeenCalledTimes(1);
    expect(screen.queryByPlaceholderText("Add tag")).toBeNull();
    unmount();
    render(TagChips, { tags: [], onadd, readonly: true });
    expect(screen.queryByLabelText("Add tag")).toBeNull();
  });
});

describe("TagEditor", () => {
  afterEach(cleanup);

  it("x rejects when onreject is set, else removes", async () => {
    const onremove = vi.fn();
    const onreject = vi.fn();
    const { unmount } = render(TagEditor, { tags: ["cat"], onadd: vi.fn(), onremove, onreject });
    await fireEvent.click(screen.getByLabelText("Reject cat"));
    expect(onreject).toHaveBeenCalledWith("cat");
    unmount();
    render(TagEditor, { tags: ["cat"], onadd: vi.fn(), onremove });
    await fireEvent.click(screen.getByLabelText("Remove cat"));
    expect(onremove).toHaveBeenCalledWith("cat");
  });
});

describe("tagSearchHref", () => {
  it("builds a search URL on the same source", () => {
    expect(tagSearchHref("big_cat")).toBe("/?q=big_cat");
    expect(tagSearchHref("a b", "books")).toBe("/?q=a_b&src=books");
  });
});
