import { describe, it, expect, vi } from "vitest";
import type { Mocked } from "vitest";
import type { Api, RulesBody } from "../api/client";
import type { ToastsLike } from "./itemView.svelte";
import { rejectTag } from "./reject";

const fixture = {
  version: 3,
  base_list: {} as never,
  reject: ["a"],
  warn: [],
  require: [],
  mapping: [],
} as RulesBody;

function makeApi(): Mocked<Pick<Api, "getRules" | "putRules">> {
  return {
    getRules: vi.fn(),
    putRules: vi.fn(),
  } as unknown as Mocked<Pick<Api, "getRules" | "putRules">>;
}

function makeToasts(): Mocked<ToastsLike> {
  return { push: vi.fn<ToastsLike["push"]>(() => 1) };
}

describe("rejectTag", () => {
  it("adds the tag and sends full put body, pushes undo toast", async () => {
    const api = makeApi() as unknown as Api;
    const toasts = makeToasts();

    (api.getRules as ReturnType<typeof vi.fn>).mockResolvedValue(fixture);
    (api.putRules as ReturnType<typeof vi.fn>).mockResolvedValue(fixture);

    await rejectTag(api, toasts, "b");

    expect(api.putRules).toHaveBeenCalledWith({
      version: 3,
      reject: ["a", "b"],
      warn: [],
      require: [],
      mapping: [],
    });
    expect(toasts.push).toHaveBeenCalledTimes(1);
    const toast = toasts.push.mock.calls[0]![0]!;
    expect(toast.kind).toBe("undo");
    expect(toast.message).toBe("Rejected tag: b");
    expect(toast.actionLabel).toBe("Undo");
    expect(toast.onAction).toBeTypeOf("function");
  });

  it("does nothing when tag is already rejected", async () => {
    const api = makeApi() as unknown as Api;
    const toasts = makeToasts();

    (api.getRules as ReturnType<typeof vi.fn>).mockResolvedValue(fixture);

    await rejectTag(api, toasts, "a");

    expect(api.putRules).not.toHaveBeenCalled();
    expect(toasts.push).not.toHaveBeenCalled();
  });

  it("pushes error toast when getRules rejects", async () => {
    const api = makeApi() as unknown as Api;
    const toasts = makeToasts();

    (api.getRules as ReturnType<typeof vi.fn>).mockRejectedValue(new Error("network"));

    await rejectTag(api, toasts, "b");

    expect(toasts.push).toHaveBeenCalledWith({
      kind: "error",
      message: "Could not reject the tag. Try again.",
    });
  });

  it("undo action calls putRules with reject back to [\"a\"]", async () => {
    const api = makeApi() as unknown as Api;
    const toasts = makeToasts();

    (api.getRules as ReturnType<typeof vi.fn>).mockResolvedValue(fixture);
    (api.putRules as ReturnType<typeof vi.fn>).mockResolvedValue(fixture);

    await rejectTag(api, toasts, "b");

    // Simulate that the tag was rejected; undo should remove it
    (api.getRules as ReturnType<typeof vi.fn>).mockResolvedValue({
      ...fixture,
      reject: ["a", "b"],
    });

    const toast = toasts.push.mock.calls[0]![0]!;
    await toast.onAction!();

    // putRules was called once for reject, once for undo
    expect(api.putRules).toHaveBeenCalledTimes(2);
    expect(api.putRules).toHaveBeenLastCalledWith({
      version: 3,
      reject: ["a"],
      warn: [],
      require: [],
      mapping: [],
    });
  });
});
