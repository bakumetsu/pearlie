// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, cleanup, fireEvent } from "@testing-library/svelte";
import PageGrid from "./PageGrid.svelte";

vi.mock("../ctx", () => ({ getRouter: () => ({ navigate: vi.fn() }) }));

afterEach(cleanup);

describe("PageGrid", () => {
  it("renders links with an outline on the last page when hrefFor is set", () => {
    const { container } = render(PageGrid, { props: { thumbTpl: "/t/{n}", count: 4, last: 2, hrefFor: (n: number) => "/r?p=" + n } });
    const thumbs = container.querySelectorAll("a.thumb");
    expect(thumbs).toHaveLength(4);
    expect(thumbs[1].classList.contains("last")).toBe(true);
    expect(thumbs[0].getAttribute("href")).toBe("/r?p=1");
    expect(container.querySelectorAll(".thumb.last")).toHaveLength(1);
  });

  it("renders buttons that call onopen and no outline when last is null", async () => {
    const onopen = vi.fn();
    const { container } = render(PageGrid, { props: { thumbTpl: "/t/{n}", count: 3, last: null, onopen } });
    const btns = container.querySelectorAll("button.thumb");
    expect(btns).toHaveLength(3);
    expect(container.querySelector(".last")).toBeNull();
    await fireEvent.click(btns[2]);
    expect(onopen).toHaveBeenCalledWith(3);
  });
});
