// @vitest-environment jsdom
import { describe, it, expect, beforeEach, afterEach, vi } from "vitest";
import { render, screen, cleanup, fireEvent } from "@testing-library/svelte";
import App from "../App.svelte";

HTMLDialogElement.prototype.showModal = function () {
  this.setAttribute("open", "");
};
HTMLDialogElement.prototype.close = function () {
  this.removeAttribute("open");
  this.dispatchEvent(new Event("close"));
};

function web(id: string) {
  return {
    source: "danbooru",
    post_id: id,
    title: `post ${id}`,
    thumb_url: `/t/${id}`,
    preview_url: `/p/${id}`,
    width: 100,
    height: 100,
    tags: [],
  };
}

describe("SeeAll web lightbox", () => {
  let saves: unknown[];

  beforeEach(() => {
    vi.stubGlobal("localStorage", { getItem: () => null, setItem: () => {}, removeItem: () => {}, clear: () => {} });
    const obs = class {
      observe() {}
      disconnect() {}
      unobserve() {}
    };
    vi.stubGlobal("IntersectionObserver", obs);
    vi.stubGlobal("ResizeObserver", obs);
    window.scrollTo = vi.fn();
    history.replaceState({}, "", "/see-all?source=danbooru&q=cat");
    saves = [];
    const json = (body: unknown, status = 200) =>
      Promise.resolve(new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } }));
    globalThis.fetch = vi.fn().mockImplementation((input: RequestInfo | URL, init?: RequestInit) => {
      const url = new URL(typeof input === "string" ? input : input instanceof URL ? input.href : input.url, "http://localhost");
      if (url.pathname === "/api/view-settings") return json({}, 404);
      if (url.pathname === "/api/search") {
        return json({
          sections: [{ id: "danbooru", items: [web("1"), web("2"), web("3")], total: 3, next_page: null, pages: 1, page_size: 60 }],
        });
      }
      if (url.pathname === "/api/save") {
        saves.push(JSON.parse(String(init?.body)));
        return json({ job_id: "j1", state: "queued" }, 202);
      }
      return json({});
    });
  });

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
  });

  async function openFirst() {
    const { container } = render(App);
    await vi.waitFor(() => expect(container.querySelectorAll(".tile.web").length).toBe(3));
    await fireEvent.click(container.querySelectorAll("button.open")[0]);
    await vi.waitFor(() => expect(document.querySelector("dialog .title")).not.toBeNull());
    return container;
  }

  const title = () => document.querySelector("dialog .title")?.textContent;

  it("tile click opens the lightbox with that item", async () => {
    await openFirst();
    expect(title()).toBe("post 1");
  });

  it("next and previous walk the grid", async () => {
    await openFirst();
    expect(screen.queryByRole("button", { name: "Previous" })).toBeNull();
    await fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(title()).toBe("post 2");
    await fireEvent.keyDown(document.querySelector("dialog")!, { key: "ArrowRight" });
    expect(title()).toBe("post 3");
    expect(screen.queryByRole("button", { name: "Next" })).toBeNull();
    await fireEvent.keyDown(document.querySelector("dialog")!, { key: "ArrowLeft" });
    expect(title()).toBe("post 2");
    await fireEvent.click(screen.getByRole("button", { name: "Previous" }));
    expect(title()).toBe("post 1");
  });

  it("Save calls the save API for the shown item", async () => {
    await openFirst();
    await fireEvent.click(screen.getByRole("button", { name: "Next" }));
    await fireEvent.click(document.querySelector("dialog .save-btn")!);
    await vi.waitFor(() => expect(saves).toEqual([{ source: "danbooru", post_id: "2" }]));
  });

  it("close (Escape closes the dialog) removes the lightbox", async () => {
    await openFirst();
    document.querySelector("dialog")!.close();
    await vi.waitFor(() => expect(document.querySelector("dialog")).toBeNull());
  });
});
