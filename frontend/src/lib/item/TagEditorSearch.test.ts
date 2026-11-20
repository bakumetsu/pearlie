// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/svelte";
import TagEditor from "./TagEditor.svelte";

const navigate = vi.fn();
vi.mock("../ctx", () => ({ getRouter: () => ({ navigate }) }));

afterEach(() => {
  cleanup();
  navigate.mockClear();
});

describe("TagEditor tag tap", () => {
  it("opens Discover on All (no src), so web rows render", async () => {
    render(TagEditor, { tags: ["big cat"], onadd: vi.fn(), onremove: vi.fn() });
    await fireEvent.click(screen.getByText("big cat"));
    expect(navigate).toHaveBeenCalledWith("/?q=big_cat");
  });
});
