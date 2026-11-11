// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup, waitFor } from "@testing-library/svelte";
import TrashRetentionCard from "./TrashRetentionCard.svelte";
import { createOptions } from "../stores/options.svelte";
import type { Api } from "../api/client";

function makeCardApi(count: number) {
  const purgePreview = vi.fn().mockResolvedValue({ count });
  const api = { purgePreview } as unknown as Api;
  return { api, purgePreview };
}

async function makeStore(
  days: number,
  putImpl?: (body: Record<string, unknown>) => Promise<Record<string, unknown>>,
) {
  const base = {
    sfw: false,
    sfw_set: true,
    player_rate: 1,
    player_rate_set: true,
    profile: "desktop",
    backdrop_strength: 60,
    backdrop_wall: true,
    backdrop_item: true,
    backdrop_lightbox: true,
    allow_blurred_tags: false,
    trash_retention_days: days,
    source_pace: {},
  };
  const impl = putImpl ?? ((body: Record<string, unknown>) => Promise.resolve({ ...base, ...body }));
  const putOptions = vi.fn(impl);
  const getOptions = vi.fn().mockResolvedValue(base);
  const api = { getOptions, putOptions } as unknown as Api;
  const store = createOptions({
    sfw: { set: vi.fn() },
    player: { loadRate: vi.fn() },
    storage: { getItem: () => null, removeItem: () => {} },
    debounceMs: 0,
  });
  await store.load(api);
  return { store, api, putOptions };
}

afterEach(() => cleanup());

describe("TrashRetentionCard", () => {
  it("shows the stored retention days", async () => {
    const { store, api } = await makeStore(7);
    render(TrashRetentionCard, { store, api: makeCardApi(0).api });
    const input = screen.getByTestId("trash-retention") as HTMLInputElement;
    expect(input.value).toBe("7");
  });

  it("raising 7 → 14: no dialog, purgePreview not called, putOptions called", async () => {
    const { store, api, putOptions } = await makeStore(7);
    const { api: cardApi, purgePreview } = makeCardApi(0);
    render(TrashRetentionCard, { store, api: cardApi });
    const input = screen.getByTestId("trash-retention") as HTMLInputElement;
    input.value = "14";
    await fireEvent.change(input);
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(purgePreview).not.toHaveBeenCalled();
    await waitFor(() => expect(putOptions).toHaveBeenCalledWith({ trash_retention_days: 14 }));
  });

  it("lowering 7 → 3 (count 3): dialog shown, Delete confirms and saves", async () => {
    const { store, api, putOptions } = await makeStore(7);
    const { api: cardApi } = makeCardApi(3);
    render(TrashRetentionCard, { store, api: cardApi });
    const input = screen.getByTestId("trash-retention") as HTMLInputElement;
    input.value = "3";
    await fireEvent.change(input);
    const dialog = screen.getByRole("dialog");
    expect(dialog.textContent).toContain("Delete 3 items now?");
    expect(putOptions).not.toHaveBeenCalled();
    await fireEvent.click(screen.getByRole("button", { name: "Delete" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(putOptions).toHaveBeenCalledWith({ trash_retention_days: 3 }));
  });

  it("count 1: singular wording", async () => {
    const { store, api } = await makeStore(7);
    const { api: cardApi } = makeCardApi(1);
    render(TrashRetentionCard, { store, api: cardApi });
    const input = screen.getByTestId("trash-retention") as HTMLInputElement;
    input.value = "3";
    await fireEvent.change(input);
    const dialog = screen.getByRole("dialog");
    expect(dialog.textContent).toContain("Delete 1 item now?");
  });

  it("lowering with count 0: no dialog, saves directly", async () => {
    const { store, api, putOptions } = await makeStore(7);
    const { api: cardApi } = makeCardApi(0);
    render(TrashRetentionCard, { store, api: cardApi });
    const input = screen.getByTestId("trash-retention") as HTMLInputElement;
    input.value = "3";
    await fireEvent.change(input);
    expect(screen.queryByRole("dialog")).toBeNull();
    await waitFor(() => expect(putOptions).toHaveBeenCalledWith({ trash_retention_days: 3 }));
  });

  it("Cancel: dialog closed, input restored, putOptions not called", async () => {
    const { store, api, putOptions } = await makeStore(7);
    const { api: cardApi } = makeCardApi(3);
    render(TrashRetentionCard, { store, api: cardApi });
    const input = screen.getByTestId("trash-retention") as HTMLInputElement;
    input.value = "3";
    await fireEvent.change(input);
    screen.getByRole("dialog");
    await fireEvent.click(screen.getByRole("button", { name: "Cancel" }));
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(input.value).toBe("7");
    expect(putOptions).not.toHaveBeenCalled();
  });

  it("Escape key: dialog closed, input restored, putOptions not called", async () => {
    const { store, api, putOptions } = await makeStore(7);
    const { api: cardApi } = makeCardApi(3);
    render(TrashRetentionCard, { store, api: cardApi });
    const input = screen.getByTestId("trash-retention") as HTMLInputElement;
    input.value = "3";
    await fireEvent.change(input);
    const dialog = screen.getByRole("dialog");
    await fireEvent.keyDown(dialog, { key: "Escape" });
    expect(screen.queryByRole("dialog")).toBeNull();
    expect(input.value).toBe("7");
    expect(putOptions).not.toHaveBeenCalled();
  });

  it("putOptions rejects: input reverts to original", async () => {
    const { store, api, putOptions } = await makeStore(7, () => Promise.reject(new Error("network")));
    const { api: cardApi } = makeCardApi(0);
    render(TrashRetentionCard, { store, api: cardApi });
    const input = screen.getByTestId("trash-retention") as HTMLInputElement;
    input.value = "14";
    await fireEvent.change(input);
    await waitFor(() => expect(putOptions).toHaveBeenCalled());
    await waitFor(() => expect(input.value).toBe("7"));
  });

  it.each(["0", "400", "2.5"])(
    "invalid input %s: alert shown, input reverts, no save",
    async (val) => {
      const { store, api, putOptions } = await makeStore(7);
      const { api: cardApi } = makeCardApi(0);
      render(TrashRetentionCard, { store, api: cardApi });
      const input = screen.getByTestId("trash-retention") as HTMLInputElement;
      input.value = val;
      await fireEvent.change(input);
      const alert = screen.getByRole("alert");
      expect(alert.textContent).toContain("Enter a whole number from 1 to 365");
      expect(input.value).toBe("7");
      expect(putOptions).not.toHaveBeenCalled();
    },
  );

  it("purgePreview rejects: error alert, no dialog, input reverts", async () => {
    const { store, api } = await makeStore(7);
    const purgePreview = vi.fn().mockRejectedValue(new Error("oops"));
    const cardApi = { purgePreview } as unknown as Api;
    render(TrashRetentionCard, { store, api: cardApi });
    const input = screen.getByTestId("trash-retention") as HTMLInputElement;
    input.value = "3";
    await fireEvent.change(input);
    const alert = screen.getByRole("alert");
    expect(alert.textContent).toContain("Could not check how many items would be deleted");
    expect(input.value).toBe("7");
    expect(screen.queryByRole("dialog")).toBeNull();
  });

  it("dialog buttons: Cancel and Delete present", async () => {
    const { store, api } = await makeStore(7);
    const { api: cardApi } = makeCardApi(3);
    render(TrashRetentionCard, { store, api: cardApi });
    const input = screen.getByTestId("trash-retention") as HTMLInputElement;
    input.value = "3";
    await fireEvent.change(input);
    expect(screen.getByRole("button", { name: "Cancel" })).toBeTruthy();
    expect(screen.getByRole("button", { name: "Delete" })).toBeTruthy();
  });
});
