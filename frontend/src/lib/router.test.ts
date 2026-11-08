import { describe, it, expect, vi } from "vitest";
import { matchRoute, hrefOf, createRouter, linkClick, ROUTES } from "./router";

describe("matchRoute", () => {
  it("matches root", () => {
    const m = matchRoute("/", "");
    expect(m.name).toBe("search");
    expect(m.params).toEqual({});
    expect(m.path).toBe("/");
  });

  it("matches trailing-slash path", () => {
    const m = matchRoute("/library/", "");
    expect(m.name).toBe("library");
  });

  it("matches deep route", () => {
    const m = matchRoute("/library/stash/images", "");
    expect(m.name).toBe("library_images");
  });

  it("matches a param route via custom routes arg and decodes values", () => {
    const routes = [...ROUTES, { name: "item", pattern: "/item/:kind/:id" }];
    const m = matchRoute("/item/photo/a%20b", "", routes);
    expect(m.name).toBe("item");
    expect(m.params).toEqual({ kind: "photo", id: "a b" });
  });

  it("parses query string", () => {
    const m = matchRoute("/", "?q=hello&page=2");
    expect(m.query.get("q")).toBe("hello");
    expect(m.query.get("page")).toBe("2");
  });

  it("returns not_found for unknown path", () => {
    const m = matchRoute("/nope", "");
    expect(m.name).toBe("not_found");
    expect(m.params).toEqual({});
  });
});

describe("hrefOf", () => {
  it("returns path unchanged when no params", () => {
    expect(hrefOf("/library")).toBe("/library");
  });

  it("builds query string and skips undefined/null", () => {
    expect(hrefOf("/library", { a: 1, b: undefined, c: null, d: "x" })).toBe("/library?a=1&d=x");
  });

  it("encodes values", () => {
    expect(hrefOf("/search", { q: "a b" })).toBe("/search?q=a+b");
  });
});

describe("createRouter", () => {
  it("navigate pushes state and notifies subscribers", () => {
    window.history.pushState(null, "", "/");
    const router = createRouter(window);
    const fn = vi.fn();
    router.subscribe(fn);
    router.navigate("/queue");
    expect(fn).toHaveBeenCalledTimes(1);
    expect(fn.mock.calls[0][0].name).toBe("queue");
    router.destroy();
  });

  it("replace does not grow history length", () => {
    window.history.pushState(null, "", "/");
    const router = createRouter(window);
    const len = window.history.length;
    router.navigate("/queue", { replace: true });
    expect(window.history.length).toBe(len);
    expect(window.location.pathname).toBe("/queue");
    router.destroy();
  });

  it("popstate notifies subscribers with new match", () => {
    window.history.replaceState(null, "", "/queue");
    const router = createRouter(window);
    const fn = vi.fn();
    router.subscribe(fn);
    window.dispatchEvent(new PopStateEvent("popstate"));
    expect(fn).toHaveBeenCalledTimes(1);
    expect(fn.mock.calls[0][0].name).toBe("queue");
    router.destroy();
  });

  it("unsubscribe stops notifications", () => {
    window.history.pushState(null, "", "/");
    const router = createRouter(window);
    const fn = vi.fn();
    const unsub = router.subscribe(fn);
    unsub();
    router.navigate("/queue");
    expect(fn).not.toHaveBeenCalled();
    router.destroy();
  });

  it("destroy removes popstate listener", () => {
    window.history.pushState(null, "", "/");
    const router = createRouter(window);
    const fn = vi.fn();
    router.subscribe(fn);
    router.destroy();
    window.dispatchEvent(new PopStateEvent("popstate"));
    expect(fn).not.toHaveBeenCalled();
  });
});

describe("linkClick", () => {
  function makeAnchor(href: string): HTMLAnchorElement {
    const a = document.createElement("a");
    a.href = href;
    document.body.appendChild(a);
    return a;
  }

  function makeEvent(a: HTMLAnchorElement, init: Partial<MouseEventInit> = {}): MouseEvent {
    const ev = new MouseEvent("click", { button: 0, cancelable: true, ...init });
    Object.defineProperty(ev, "currentTarget", { value: a });
    return ev;
  }

  it("left-click on internal link navigates and prevents default", () => {
    window.history.pushState(null, "", "/");
    const router = createRouter(window);
    const a = makeAnchor("/library");
    const ev = makeEvent(a);
    linkClick(ev, router);
    expect(window.location.pathname).toBe("/library");
    expect(ev.defaultPrevented).toBe(true);
    a.remove();
    router.destroy();
  });

  it("ctrl-click does not navigate", () => {
    window.history.pushState(null, "", "/");
    const router = createRouter(window);
    const a = makeAnchor("/library");
    const ev = makeEvent(a, { ctrlKey: true });
    linkClick(ev, router);
    expect(window.location.pathname).toBe("/");
    expect(ev.defaultPrevented).toBe(false);
    a.remove();
    router.destroy();
  });

  it("external link does not navigate", () => {
    window.history.pushState(null, "", "/");
    const router = createRouter(window);
    const a = makeAnchor("https://example.com/x");
    const ev = makeEvent(a);
    linkClick(ev, router);
    expect(window.location.pathname).toBe("/");
    expect(ev.defaultPrevented).toBe(false);
    a.remove();
    router.destroy();
  });
});
