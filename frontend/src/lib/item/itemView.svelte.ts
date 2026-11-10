import { ApiError } from "../api/client";
import type { Api, Kind, LibraryItem, WebItem, LibraryItemDetail } from "../api/client";
import { itemKey } from "./kinds";
import { tagToString, stringToTag, addTags, removeTag } from "./tags";

export interface GridLike {
  removeById(id: string): { item: LibraryItem | WebItem; index: number } | null;
  restore(entry: { item: LibraryItem | WebItem; index: number }): void;
  updateById?(id: string, patch: Partial<LibraryItem>): boolean;
  page?: number;
}
export interface ToastsLike {
  push(t: { kind: "info" | "error" | "undo"; message: string; actionLabel?: string; onAction?: () => void }): number;
}
export type ItemDeps = { api: Api; grid: GridLike; toasts: ToastsLike; tagDebounceMs?: number };
export type ItemStatus = "loading" | "ready" | "gone" | "error";

export function createItemView(deps: ItemDeps) {
  const state = $state({
    detail: null as LibraryItemDetail | null,
    status: "loading" as ItemStatus,
    kind: null as Kind | null,
  });
  let currentId: string | null = null;
  let requestCounter = 0;
  let tagBase: string[] | null = null;
  let tagTimer: ReturnType<typeof setTimeout> | null = null;

  return {
    get detail(): LibraryItemDetail | null {
      return state.detail;
    },
    get status(): ItemStatus {
      return state.status;
    },
    get tagStrings(): string[] {
      return state.detail?.tags?.map(tagToString) ?? [];
    },

    async load(kind: Kind, id: string): Promise<void> {
      const reqId = ++requestCounter;
      state.status = "loading";
      state.detail = null;
      state.kind = kind;
      currentId = id;

      try {
        const result = await deps.api.getItem(kind, id);
        if (reqId !== requestCounter) return;
        state.detail = result;
        state.status = "ready";
      } catch (e) {
        if (reqId !== requestCounter) return;
        if (e instanceof ApiError && e.status === 404) {
          state.status = "gone";
        } else {
          state.status = "error";
        }
      }
    },

    async setRating(n: number): Promise<void> {
      if (!state.detail || !state.kind || !currentId) return;
      const d = state.detail;
      const oldRating = d.rating;
      const newRating: number | null = oldRating === n ? null : n;
      d.rating = newRating;
      const kind = state.kind;
      const id = currentId;

      try {
        await deps.api.patchItem(kind, id, { rating: newRating });
        deps.grid.updateById?.(itemKey({ kind: d.kind, id: d.id }), { rating: newRating });
      } catch {
        d.rating = oldRating;
        deps.toasts.push({ kind: "error", message: "Could not save the rating. Try again." });
      }
    },

    async toggleFavorite(): Promise<void> {
      if (!state.detail || !state.kind || !currentId) return;
      const oldFav = state.detail.favorite;
      const newFav = !oldFav;
      state.detail.favorite = newFav;

      try {
        await deps.api.patchItem(state.kind, currentId, { favorite: newFav });
      } catch {
        state.detail.favorite = oldFav;
        deps.toasts.push({ kind: "error", message: "Could not update the favorite. Try again." });
      }
    },

    setTagsFromStrings(next: string[]): void {
      if (!state.detail || !state.kind || !currentId) return;
      if (tagBase === null) {
        tagBase = (state.detail.tags ?? []).map(tagToString);
      }
      state.detail.tags = next.map(stringToTag);

      if (tagTimer !== null) clearTimeout(tagTimer);
      const kind = state.kind;
      const id = currentId;
      tagTimer = setTimeout(async () => {
        tagTimer = null;
        try {
          await deps.api.patchItem(kind, id, { tags: next });
          tagBase = null;
        } catch {
          if (tagBase !== null && state.detail) {
            state.detail.tags = tagBase.map(stringToTag);
          }
          tagBase = null;
          deps.toasts.push({ kind: "error", message: "Could not save the tags. Try again." });
        }
      }, deps.tagDebounceMs ?? 500);
    },

    addTagInput(text: string): void {
      const next = addTags(this.tagStrings, text);
      if (JSON.stringify(next) !== JSON.stringify(this.tagStrings)) {
        this.setTagsFromStrings(next);
      }
    },

    removeTagByName(tag: string): void {
      this.setTagsFromStrings(removeTag(this.tagStrings, tag));
    },

    async remove(): Promise<void> {
      if (!state.detail || !state.kind || !currentId) return;
      const d = state.detail;

      let trashResult: Awaited<ReturnType<Api["deleteItem"]>>;
      try {
        trashResult = await deps.api.deleteItem(state.kind, currentId);
      } catch {
        deps.toasts.push({ kind: "error", message: "Could not move to trash. Try again." });
        return;
      }

      const page = deps.grid.page;
      const entry = deps.grid.removeById(itemKey({ kind: d.kind, id: d.id }));
      const token = trashResult.token;

      deps.toasts.push({
        kind: "undo",
        message: "Moved to trash: " + d.title,
        actionLabel: "Undo",
        onAction: async () => {
          try {
            await deps.api.restore(token);
            if (entry !== null && deps.grid.page === page) deps.grid.restore(entry);
            deps.toasts.push({ kind: "info", message: "Restored" });
          } catch (e) {
            if (e instanceof ApiError && e.status === 404) {
              deps.toasts.push({ kind: "error", message: "Can't undo any more" });
            } else {
              deps.toasts.push({ kind: "error", message: "Could not undo. Try again." });
            }
          }
        },
      });

      state.status = "gone";
    },
  };
}
