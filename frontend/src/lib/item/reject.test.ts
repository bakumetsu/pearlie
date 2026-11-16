import { describe, it, expect, vi } from "vitest";
import type { Mocked } from "vitest";
import type { Api } from "../api/client";
import type { ToastsLike } from "./itemView.svelte";
import { rejectTag } from "./reject";

function makeApi(): Mocked<Pick<Api, "rejectTag" | "unrejectTag">> {
  return { rejectTag: vi.fn(), unrejectTag: vi.fn() } as unknown as Mocked<Pick<Api, "rejectTag" | "unrejectTag">>;
}

function makeToasts(): Mocked<ToastsLike> {
  return { push: vi.fn<ToastsLike["push"]>(() => 1) };
}

describe("rejectTag", () => {
  it("calls the backend and pushes an undo toast", async () => {
    const api = makeApi();
    const toasts = makeToasts();
    api.rejectTag.mockResolvedValue({ added: true, version: 2 });

    await rejectTag(api as unknown as Api, toasts, "b");

    expect(api.rejectTag).toHaveBeenCalledWith("b");
    expect(toasts.push).toHaveBeenCalledTimes(1);
    const toast = toasts.push.mock.calls[0]![0]!;
    expect(toast.kind).toBe("undo");
    expect(toast.message).toBe("Rejected tag: b");
    expect(toast.actionLabel).toBe("Undo");
  });

  it("shows nothing when the tag was already rejected", async () => {
    const api = makeApi();
    const toasts = makeToasts();
    api.rejectTag.mockResolvedValue({ added: false, version: 2 });

    await rejectTag(api as unknown as Api, toasts, "a");

    expect(toasts.push).not.toHaveBeenCalled();
  });

  it("pushes an error toast when the call fails", async () => {
    const api = makeApi();
    const toasts = makeToasts();
    api.rejectTag.mockRejectedValue(new Error("network"));

    await rejectTag(api as unknown as Api, toasts, "b");

    expect(toasts.push).toHaveBeenCalledWith({
      kind: "error",
      message: "Could not reject the tag. Try again.",
    });
  });

  it("undo removes only that tag; a failure shows the error toast", async () => {
    const api = makeApi();
    const toasts = makeToasts();
    api.rejectTag.mockResolvedValue({ added: true, version: 2 });
    api.unrejectTag.mockResolvedValue({ removed: true, version: 3 });

    await rejectTag(api as unknown as Api, toasts, "b");
    const toast = toasts.push.mock.calls[0]![0]!;
    await toast.onAction!();
    expect(api.unrejectTag).toHaveBeenCalledWith("b");

    api.unrejectTag.mockRejectedValue(new Error("gone"));
    await toast.onAction!();
    expect(toasts.push).toHaveBeenLastCalledWith({ kind: "error", message: "Can't undo any more" });
  });
});
