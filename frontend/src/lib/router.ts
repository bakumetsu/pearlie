
export type RouteDef = { name: string; pattern: string };

export const ROUTES: RouteDef[] = [
  { name: "discover", pattern: "/" },
  { name: "discover", pattern: "/discover" },
  { name: "home", pattern: "/home" },
  { name: "library", pattern: "/library" },
  { name: "seeall", pattern: "/see-all" },
  { name: "library_images", pattern: "/library/stash/images" },
  { name: "library_videos", pattern: "/library/stash/videos" },
  { name: "library_series", pattern: "/library/komga/series" },
  { name: "library_books", pattern: "/library/komga/books" },
  { name: "item", pattern: "/item/:kinds/:id" },
  { name: "read", pattern: "/read/:bookId" },
  { name: "queue", pattern: "/queue" },
  { name: "trash", pattern: "/trash" },
  { name: "options", pattern: "/options" },
  { name: "options", pattern: "/options/:section" },
  { name: "option_redirect", pattern: "/option" },
  { name: "rules_redirect", pattern: "/rules" },
];

export type Match = { name: string; params: Record<string, string>; query: URLSearchParams; path: string };

export function matchRoute(pathname: string, search: string, routes: RouteDef[] = ROUTES): Match {
  const p = pathname !== "/" && pathname.endsWith("/") ? pathname.slice(0, -1) : pathname;
  const pathSegs = p.split("/").filter(Boolean);
  for (const route of routes) {
    const patSegs = route.pattern.split("/").filter(Boolean);
    if (patSegs.length !== pathSegs.length) continue;
    const params: Record<string, string> = {};
    let ok = true;
    for (let i = 0; i < patSegs.length; i++) {
      if (patSegs[i].startsWith(":")) {
        params[patSegs[i].slice(1)] = decodeURIComponent(pathSegs[i]);
      } else if (patSegs[i] !== pathSegs[i]) {
        ok = false;
        break;
      }
    }
    if (ok) return { name: route.name, params, query: new URLSearchParams(search), path: pathname };
  }
  return { name: "not_found", params: {}, query: new URLSearchParams(search), path: pathname };
}

export function hrefOf(path: string, params?: Record<string, string | number | boolean | null | undefined>): string {
  if (!params) return path;
  const qs = new URLSearchParams();
  for (const [k, v] of Object.entries(params)) {
    if (v !== null && v !== undefined) qs.set(k, String(v));
  }
  const s = qs.toString();
  return s ? `${path}?${s}` : path;
}

export type Router = {
  current(): Match;
  navigate(href: string, opts?: { replace?: boolean }): void;
  canGoBack(): boolean;
  subscribe(fn: (m: Match) => void): () => void;
  destroy(): void;
};

export function createRouter(win: Window = window): Router {
  const subs = new Set<(m: Match) => void>();
  function notify() {
    const m = matchRoute(win.location.pathname, win.location.search);
    subs.forEach((fn) => fn(m));
  }
  function onPop() { notify(); }
  win.addEventListener("popstate", onPop);
  return {
    current: () => matchRoute(win.location.pathname, win.location.search),
    navigate(href: string, opts?: { replace?: boolean }) {
      if (opts?.replace) win.history.replaceState({ ...(win.history.state ?? {}) }, "", href);
      else win.history.pushState({ ...(win.history.state ?? {}), depth: (win.history.state?.depth ?? 0) + 1 }, "", href);
      notify();
    },
    canGoBack: () => (win.history.state?.depth ?? 0) > 0,
    subscribe(fn: (m: Match) => void) {
      subs.add(fn);
      return () => { subs.delete(fn); };
    },
    destroy() {
      win.removeEventListener("popstate", onPop);
      subs.clear();
    },
  };
}

export function linkClick(e: MouseEvent, router: Router): void {
  const a = e.currentTarget as HTMLAnchorElement;
  if (e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.defaultPrevented) return;
  if (a.target || a.hasAttribute("download")) return;
  if (new URL(a.href).origin !== window.location.origin) return;
  e.preventDefault();
  router.navigate(a.pathname + a.search);
}
