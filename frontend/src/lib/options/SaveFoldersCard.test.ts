// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup, waitFor } from "@testing-library/svelte";
import SaveFoldersCard from "./SaveFoldersCard.svelte";
import { ApiError } from "../api/client";
import type { Api, Destinations } from "../api/client";

function dest(over: Partial<Destinations> = {}): Destinations {
  return {
    default_folder: "/mnt/media/stash/Other",
    items: [],
    sites: ["danbooru", "gelbooru"],
    library_paths: ["/mnt/media/stash/rule34", "/mnt/media/stash/Other"],
    library_error: null,
    prefix_pearlie: "",
    prefix_stash: "",
    ...over,
  };
}

function makeApi(over: Partial<Record<keyof Api, unknown>> = {}) {
  const api = {
    getDestinations: vi.fn().mockResolvedValue(dest()),
    putDefaultFolder: vi.fn(),
    putSiteFolder: vi.fn(),
    deleteSiteFolder: vi.fn(),
    ...over,
  };
  return { api: api as unknown as Api, mocks: api };
}

afterEach(() => cleanup());

describe("SaveFoldersCard", () => {
  it("loads the default folder, per-site rows and library path hints", async () => {
    const { api } = makeApi({
      getDestinations: vi.fn().mockResolvedValue(
        dest({ items: [{ site: "danbooru", folder: "/mnt/media/stash/rule34" }] }),
      ),
    });
    render(SaveFoldersCard, { api });
    const def = (await screen.findByTestId("folder-default")) as HTMLInputElement;
    expect(def.value).toBe("/mnt/media/stash/Other");
    expect((screen.getByTestId("folder-danbooru") as HTMLInputElement).value).toBe("/mnt/media/stash/rule34");
    expect((screen.getByTestId("folder-gelbooru") as HTMLInputElement).value).toBe("");
    expect(screen.getByTestId("library-paths").textContent).toContain("/mnt/media/stash/rule34");
  });

  it("saves the default folder", async () => {
    const put = vi.fn().mockResolvedValue(dest({ default_folder: "/mnt/media/stash/rule34" }));
    const { api } = makeApi({ putDefaultFolder: put });
    render(SaveFoldersCard, { api });
    const input = (await screen.findByTestId("folder-default")) as HTMLInputElement;
    await fireEvent.input(input, { target: { value: "/mnt/media/stash/rule34" } });
    await fireEvent.click(screen.getByTestId("save-default"));
    await waitFor(() => expect(put).toHaveBeenCalledWith("/mnt/media/stash/rule34"));
    expect(await screen.findByText("Saved")).toBeTruthy();
  });

  it("saves a per-site folder and clears it with an empty value", async () => {
    const put = vi.fn().mockResolvedValue(
      dest({ items: [{ site: "gelbooru", folder: "/mnt/media/stash/rule34" }] }),
    );
    const del = vi.fn().mockResolvedValue(dest());
    const { api } = makeApi({ putSiteFolder: put, deleteSiteFolder: del });
    render(SaveFoldersCard, { api });
    const input = (await screen.findByTestId("folder-gelbooru")) as HTMLInputElement;
    await fireEvent.input(input, { target: { value: "/mnt/media/stash/rule34" } });
    await fireEvent.click(screen.getByTestId("save-gelbooru"));
    await waitFor(() => expect(put).toHaveBeenCalledWith("gelbooru", "/mnt/media/stash/rule34"));
    await fireEvent.input(input, { target: { value: "" } });
    await fireEvent.click(screen.getByTestId("save-gelbooru"));
    await waitFor(() => expect(del).toHaveBeenCalledWith("gelbooru"));
  });

  it("shows the outside_library error inline and keeps the draft", async () => {
    const put = vi
      .fn()
      .mockRejectedValue(new ApiError(400, "outside_library", "folder is not inside a Stash library path"));
    const { api } = makeApi({ putDefaultFolder: put });
    render(SaveFoldersCard, { api });
    const input = (await screen.findByTestId("folder-default")) as HTMLInputElement;
    await fireEvent.input(input, { target: { value: "/etc" } });
    await fireEvent.click(screen.getByTestId("save-default"));
    const alert = await screen.findByRole("alert");
    expect(alert.textContent).toBe("folder is not inside a Stash library path");
    expect(input.value).toBe("/etc");
  });

  it("shows when Stash library paths cannot be read", async () => {
    const { api } = makeApi({
      getDestinations: vi.fn().mockResolvedValue(dest({ library_paths: [], library_error: "Stash is not configured" })),
    });
    render(SaveFoldersCard, { api });
    expect((await screen.findByRole("status")).textContent).toContain("Stash is not configured");
  });
});
