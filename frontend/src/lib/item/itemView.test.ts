import { describe, it, expect, vi, afterEach } from "vitest";
import type { Mocked } from "vitest";
import { ApiError } from "../api/client";
import type { Api, LibraryItem, LibraryItemDetail } from "../api/client";
import type { GridLike, ToastsLike } from "./itemView.svelte";
import { createItemView } from "./itemView.svelte";

// ─── fakes ───────────────────────────────────────────────────────────────────

function makeApi() {
  return {
    getItem: vi.fn(),
    patchItem: vi.fn(),
    deleteItem: vi.fn(),
    restore: vi.fn(),
  } as unknown as Mocked<Pick<Api, "getItem" | "patchItem" | "deleteItem" | "restore">>;
}

function makeGrid(): Mocked<GridLike> {
  return { removeById: vi.fn(), restore: vi.fn(), updateById: vi.fn() };
}

function makeToasts(): Mocked<ToastsLike> {
  return { push: vi.fn<ToastsLike["push"]>(() => 1) };
}

const gridItem = { kind: "image", id: "5", title: "Plate 5", thumb_url: "", favorite: false, added_at: "" } as LibraryItem;

const detailFixture: LibraryItemDetail = {
  kind: "image",
  id: "5",
  title: "Plate 5",
  thumb_url: "",
  rating: 3,
  favorite: false,
  tags: [{ name: "a", scope: null }, { name: "x", scope: "artist" }],
  added_at: "2026-01-01",
} as LibraryItemDetail;

// ─── setup helpers ───────────────────────────────────────────────────────────

function setup(opts?: { tagDebounceMs?: number }) {
  const api = makeApi();
  const grid = makeGrid();
  const toasts = makeToasts();
  const view = createItemView({ api: api as unknown as Api, grid, toasts, tagDebounceMs: opts?.tagDebounceMs });

  // convenience: pre-load with the fixture
  async function preLoad() {
    api.getItem.mockResolvedValue(detailFixture);
    await view.load("images", "5");
  }

  return { api, grid, toasts, view, preLoad };
}

// ─── tests ───────────────────────────────────────────────────────────────────

describe("createItemView", () => {
  afterEach(() => {
    vi.useRealTimers();
    vi.restoreAllMocks();
  });

  describe("load", () => {
    it("resolves to ready with detail", async () => {
      const { api, view } = setup();
      api.getItem.mockResolvedValue(detailFixture);

      await view.load("images", "5");

      expect(view.status).toBe("ready");
      expect(view.detail).toEqual(detailFixture);
      expect(api.getItem).toHaveBeenCalledWith("images", "5");
    });

    it("maps ApiError 404 to gone", async () => {
      const { api, view } = setup();
      api.getItem.mockRejectedValue(new ApiError(404, "not_found", "gone"));

      await view.load("images", "5");

      expect(view.status).toBe("gone");
      expect(view.detail).toBeNull();
    });
  });

  describe("setRating", () => {
    it("optimistically sets rating and PATCHes", async () => {
      const { api, view, preLoad } = setup();
      await preLoad();

      await view.setRating(4);

      expect(view.detail?.rating).toBe(4);
      expect(api.patchItem).toHaveBeenCalledWith("images", "5", { rating: 4 });
    });

    it("clears rating when clicking the same value", async () => {
      const { api, view, preLoad } = setup();
      await preLoad(); // rating is 3

      await view.setRating(3);

      expect(view.detail?.rating).toBeNull();
      expect(api.patchItem).toHaveBeenCalledWith("images", "5", { rating: null });
    });

    it("reverts on failure and shows error toast", async () => {
      const { api, toasts, view, preLoad } = setup();
      await preLoad();
      api.patchItem.mockRejectedValue(new Error("network"));

      await view.setRating(4);

      expect(view.detail?.rating).toBe(3); // reverted
      expect(toasts.push).toHaveBeenCalledWith({
        kind: "error",
        message: "Could not save the rating. Try again.",
      });
    });

    it("calls updateById on success", async () => {
      const { grid, view, preLoad } = setup();
      await preLoad();

      await view.setRating(4);

      expect(grid.updateById).toHaveBeenCalledWith(expect.any(String), { rating: 4 });
    });

    it("does not call updateById when patchItem rejects", async () => {
      const { api, grid, view, preLoad } = setup();
      await preLoad();
      api.patchItem.mockRejectedValue(new Error("network"));

      await view.setRating(4);

      expect(grid.updateById).not.toHaveBeenCalled();
    });

    it("rejecting patch after loading another item does not corrupt the new detail", async () => {
      const { api, view } = setup();
      api.getItem.mockResolvedValue(detailFixture);
      await view.load("images", "5"); // rating is 3

      let rejectPatch!: (e: unknown) => void;
      api.patchItem.mockReturnValue(new Promise((_, rej) => { rejectPatch = rej; }));

      const ratingPromise = view.setRating(4); // suspends at await patchItem

      const newDetail = { ...detailFixture, id: "6", rating: null } as LibraryItemDetail;
      api.getItem.mockResolvedValue(newDetail);
      await view.load("images", "6");

      rejectPatch(new Error("network"));
      await ratingPromise;

      expect(view.detail?.id).toBe("6");
      expect(view.detail?.rating).toBeNull();
    });
  });

  describe("toggleFavorite", () => {
    it("toggles to true on success", async () => {
      const { api, view, preLoad } = setup();
      await preLoad(); // favorite is false

      await view.toggleFavorite();

      expect(view.detail?.favorite).toBe(true);
      expect(api.patchItem).toHaveBeenCalledWith("images", "5", { favorite: true });
    });

    it("reverts on failure and shows error toast", async () => {
      const { api, toasts, view, preLoad } = setup();
      await preLoad();
      api.patchItem.mockRejectedValue(new Error("network"));

      await view.toggleFavorite();

      expect(view.detail?.favorite).toBe(false);
      expect(toasts.push).toHaveBeenCalledWith({
        kind: "error",
        message: "Could not update the favorite. Try again.",
      });
    });
  });

  describe("tags (debounced)", () => {
    it("is optimistic, debounces at 500 ms, sends full list", async () => {
      vi.useFakeTimers();
      const { api, view, preLoad } = setup();
      await preLoad();

      view.addTagInput("b");

      // optimistic
      expect(view.tagStrings).toEqual(["a", "artist:x", "b"]);
      expect(api.patchItem).not.toHaveBeenCalled();

      // 499 ms – still no PATCH
      vi.advanceTimersByTime(499);
      expect(api.patchItem).not.toHaveBeenCalled();

      // 500 ms – one PATCH with the full list
      vi.advanceTimersByTime(1);
      expect(api.patchItem).toHaveBeenCalledTimes(1);
      expect(api.patchItem).toHaveBeenCalledWith("images", "5", { tags: ["a", "artist:x", "b"] });
    });

    it("coalesces two quick changes into one PATCH", async () => {
      vi.useFakeTimers();
      const { api, view, preLoad } = setup();
      await preLoad();

      view.addTagInput("b");
      view.addTagInput("c");

      vi.advanceTimersByTime(500);

      expect(api.patchItem).toHaveBeenCalledTimes(1);
      expect(api.patchItem).toHaveBeenCalledWith("images", "5", { tags: ["a", "artist:x", "b", "c"] });
    });

    it("reverts tags on failure", async () => {
      vi.useFakeTimers();
      const { api, toasts, view, preLoad } = setup();
      await preLoad();
      api.patchItem.mockRejectedValue(new Error("server"));

      view.addTagInput("b");
      await vi.advanceTimersByTimeAsync(500);

      expect(view.tagStrings).toEqual(["a", "artist:x"]); // reverted
      expect(toasts.push).toHaveBeenCalledWith({
        kind: "error",
        message: "Could not save the tags. Try again.",
      });
    });
  });

  describe("remove", () => {
    const trashResult = { token: "tok-1", expires_at: "2026-02-01", retention_days: 30, item: { kind: "image" as const, id: "5", title: "Plate 5" } };

    it("deletes, removes from grid, pushes undo toast, sets gone", async () => {
      const { api, grid, toasts, view, preLoad } = setup();
      await preLoad();
      api.deleteItem.mockResolvedValue(trashResult);
      const entry = { item: gridItem, index: 0 };
      grid.removeById.mockReturnValue(entry);

      await view.remove();

      expect(api.deleteItem).toHaveBeenCalledWith("images", "5");
      expect(grid.removeById).toHaveBeenCalledWith("image:5");
      expect(view.status).toBe("gone");
      expect(toasts.push).toHaveBeenCalledWith(
        expect.objectContaining({ kind: "undo", message: "Moved to trash: Plate 5", actionLabel: "Undo" }),
      );
    });

    it("onAction restores and re-inserts into grid", async () => {
      const { api, grid, toasts, view, preLoad } = setup();
      await preLoad();
      api.deleteItem.mockResolvedValue(trashResult);
      api.restore.mockResolvedValue({ item: gridItem });
      const entry = { item: gridItem, index: 0 };
      grid.removeById.mockReturnValue(entry);

      await view.remove();

      const undoToast = toasts.push.mock.calls.at(-1)?.[0];
      expect(undoToast?.kind).toBe("undo");

      await undoToast!.onAction!();

      expect(api.restore).toHaveBeenCalledWith("tok-1");
      expect(grid.restore).toHaveBeenCalledWith(entry);
      expect(toasts.push).toHaveBeenCalledWith({ kind: "info", message: "Restored" });
    });

    it("onAction restores on the server but skips grid.restore when the grid page changed", async () => {
      const { api, grid, toasts, view, preLoad } = setup();
      const g = grid as unknown as { page?: number };
      g.page = 1;
      await preLoad();
      api.deleteItem.mockResolvedValue(trashResult);
      api.restore.mockResolvedValue({ item: gridItem });
      grid.removeById.mockReturnValue({ item: gridItem, index: 0 });
      await view.remove();
      const undoToast = toasts.push.mock.calls.at(-1)?.[0];
      g.page = 2;
      await undoToast!.onAction!();
      expect(api.restore).toHaveBeenCalledWith("tok-1");
      expect(grid.restore).not.toHaveBeenCalled();
    });

    it("onAction with 404 restore shows 'Can't undo any more' and skips grid.restore", async () => {
      const { api, grid, toasts, view, preLoad } = setup();
      await preLoad();
      api.deleteItem.mockResolvedValue(trashResult);
      api.restore.mockRejectedValue(new ApiError(404, "expired", "gone"));
      vi.mocked(grid.removeById).mockReturnValue(null);

      await view.remove();

      const undoToast = vi.mocked(toasts.push).mock.calls.at(-1)?.[0];
      await undoToast!.onAction!();

      expect(toasts.push).toHaveBeenCalledWith({ kind: "error", message: "Can't undo any more" });
      expect(grid.restore).not.toHaveBeenCalled();
    });
  });
});
