// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup, waitFor } from "@testing-library/svelte";
import TrashFolderCard from "./TrashFolderCard.svelte";
import { ApiError } from "../api/client";
import type { Api, TrashFolder } from "../api/client";

const base: TrashFolder = { path: "/t", source: "env", env_path: "/t", state: "ok", items: 0 };

function make(folder: Partial<TrashFolder> = {}, extra: Partial<Record<keyof Api, unknown>> = {}) {
  const f = { ...base, ...folder };
  const api = {
    trashFolder: vi.fn().mockResolvedValue(f),
    setTrashFolder: vi.fn().mockResolvedValue(f),
    createTrashFolder: vi.fn().mockResolvedValue(f),
    ...extra,
  } as unknown as Api;
  render(TrashFolderCard, { api });
  return api;
}

afterEach(cleanup);

describe("TrashFolderCard", () => {
  it("shows OK status and no Create button", async () => {
    make();
    await waitFor(() => expect(screen.getByTestId("trash-folder-status").textContent).toContain("OK"));
    expect(screen.queryByTestId("trash-folder-create")).toBeNull();
  });

  it("shows Create when the folder is missing and calls create", async () => {
    const api = make({ state: "missing" });
    const btn = await screen.findByTestId("trash-folder-create");
    expect(screen.getByTestId("trash-folder-status").textContent).toContain("missing");
    await fireEvent.click(btn);
    expect(api.createTrashFolder).toHaveBeenCalledWith("");
  });

  it("shows Create for a typed path after folder_missing and creates that path", async () => {
    const api = make({}, {
      setTrashFolder: vi.fn().mockRejectedValue(new ApiError(422, "folder_missing", "x")),
    });
    const input = (await screen.findByTestId("trash-folder-path")) as HTMLInputElement;
    await waitFor(() => expect(input.value).toBe("/t"));
    await fireEvent.input(input, { target: { value: "/new" } });
    expect(screen.queryByTestId("trash-folder-create")).toBeNull();
    await fireEvent.click(screen.getByTestId("trash-folder-save"));
    const btn = await screen.findByTestId("trash-folder-create");
    await fireEvent.click(btn);
    expect(api.createTrashFolder).toHaveBeenCalledWith("/new");
  });

  it("locks the field and hides Save while the trash has items", async () => {
    make({ items: 2 });
    const input = (await screen.findByTestId("trash-folder-path")) as HTMLInputElement;
    await waitFor(() => expect(screen.getByTestId("trash-folder-status").textContent).toContain("Locked: 2"));
    expect(input.disabled).toBe(true);
    expect(screen.queryByTestId("trash-folder-save")).toBeNull();
  });

  it("save sends the typed path and shows the stored source", async () => {
    const api = make({}, {
      setTrashFolder: vi.fn().mockResolvedValue({ ...base, path: "/new", source: "stored" }),
    });
    const input = (await screen.findByTestId("trash-folder-path")) as HTMLInputElement;
    await waitFor(() => expect(input.value).toBe("/t"));
    await fireEvent.input(input, { target: { value: "/new" } });
    await fireEvent.click(screen.getByTestId("trash-folder-save"));
    expect(api.setTrashFolder).toHaveBeenCalledWith("/new");
    await waitFor(() => expect(screen.getByTestId("trash-folder-status").textContent).toContain("set here"));
  });

  it("maps an error code to a message", async () => {
    make({}, { setTrashFolder: vi.fn().mockRejectedValue(new ApiError(422, "other_volume", "x")) });
    await screen.findByTestId("trash-folder-save");
    await fireEvent.click(screen.getByTestId("trash-folder-save"));
    const err = await screen.findByTestId("trash-folder-error");
    expect(err.textContent).toContain("same drive");
  });
});
