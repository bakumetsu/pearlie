import { render, screen, fireEvent, cleanup } from "@testing-library/svelte";
import { describe, it, expect, vi, afterEach } from "vitest";
import Rail from "./Rail.svelte";

afterEach(cleanup);

const base = {
  fit: "both", mode: "single", fullscreen: false, settingsOpen: false, zoom: 100, hidden: false,
  onback: vi.fn(), onsettings: vi.fn(), onfit: vi.fn(), onmode: vi.fn(), onfullscreen: vi.fn(),
  onhelp: vi.fn(), onzoomin: vi.fn(), onzoomout: vi.fn(), onzoomreset: vi.fn(),
} as const;

describe("Rail save slot", () => {
  it("has no Save button without a slot", () => {
    render(Rail, { ...base });
    expect(screen.queryByRole("button", { name: "Save" })).toBeNull();
  });

  it("idle Save calls onsave; queued is disabled; in library is a link", async () => {
    const onsave = vi.fn();
    const r = render(Rail, { ...base, save: { state: "idle", onsave } });
    await fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(onsave).toHaveBeenCalledOnce();
    await r.rerender({ ...base, save: { state: "queued", onsave } });
    expect((screen.getByRole("button", { name: "Saving" }) as HTMLButtonElement).disabled).toBe(true);
    await r.rerender({ ...base, save: { state: "in_library", href: "/item/books/b1", onsave } });
    expect(screen.getByRole("link", { name: "In library" }).getAttribute("href")).toBe("/item/books/b1");
  });
});
