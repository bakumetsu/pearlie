// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/svelte";
import ImageViewerCard from "./ImageViewerCard.svelte";
import { BACKDROP_DEFAULTS } from "./backdrop";
import type { OptionsStore } from "../stores/options.svelte";
import type { Api, Options } from "../api/client";

vi.mock("../stores/options.svelte", async (importOriginal) => {
	const actual = await importOriginal<typeof import("../stores/options.svelte")>();
	return { ...actual, options: { values: null, set: vi.fn() } };
});
vi.mock("../stores/toasts.svelte", () => ({ toasts: { push: vi.fn() } }));

function makeStore(values: Record<string, unknown> | null) {
	return { values, set: vi.fn() } as unknown as OptionsStore & { set: ReturnType<typeof vi.fn> };
}

// A real (reactive) store with a mocked API, so cards see their own changes
async function makeRealStore(values: Record<string, unknown>) {
	const { createOptions } = await import("../stores/options.svelte");
	const opts = { sfw: false, sfw_set: true, player_rate: 1, player_rate_set: true, source_pace: {}, ...values } as unknown as Options;
	const api = { getOptions: vi.fn(async () => opts), putOptions: vi.fn(async () => opts) } as unknown as Api;
	const store = createOptions({ sfw: { set: vi.fn() }, player: { loadRate: vi.fn() }, storage: { getItem: () => null, removeItem: () => {} } });
	await store.load(api);
	const set = vi.spyOn(store, "set");
	return Object.assign(store, { set }) as OptionsStore & { set: typeof set };
}

beforeEach(() => {
	vi.clearAllMocks();
});

afterEach(() => {
	cleanup();
});

describe("ImageViewerCard", () => {
	it("slider input calls set with the number", () => {
		const store = makeStore({
			backdrop_strength: BACKDROP_DEFAULTS.strength,
			backdrop_wall: BACKDROP_DEFAULTS.wall,
			backdrop_item: BACKDROP_DEFAULTS.item,
			backdrop_lightbox: BACKDROP_DEFAULTS.lightbox,
		});
		render(ImageViewerCard, { store });

		const slider = screen.getByLabelText("Backdrop strength");
		fireEvent.input(slider, { target: { value: "80" } });

		expect(store.set).toHaveBeenCalledWith({ backdrop_strength: 80 });
	});

	it("clicking each switch calls set with the negated value and flips aria-checked", async () => {
		const store = await makeRealStore({
			backdrop_strength: BACKDROP_DEFAULTS.strength,
			backdrop_wall: true,
			backdrop_item: true,
			backdrop_lightbox: true,
		});
		render(ImageViewerCard, { store });

		const wall = screen.getByRole("switch", { name: "Show backdrop in wall overlay" });
		expect(wall.getAttribute("aria-checked")).toBe("true");
		await fireEvent.click(wall);
		expect(store.set).toHaveBeenCalledWith({ backdrop_wall: false });
		expect(wall.getAttribute("aria-checked")).toBe("false");

		const item = screen.getByRole("switch", { name: "Show backdrop on item page" });
		expect(item.getAttribute("aria-checked")).toBe("true");
		await fireEvent.click(item);
		expect(store.set).toHaveBeenCalledWith({ backdrop_item: false });
		expect(item.getAttribute("aria-checked")).toBe("false");

		const lightbox = screen.getByRole("switch", { name: "Show backdrop in lightbox" });
		expect(lightbox.getAttribute("aria-checked")).toBe("true");
		await fireEvent.click(lightbox);
		expect(store.set).toHaveBeenCalledWith({ backdrop_lightbox: false });
		expect(lightbox.getAttribute("aria-checked")).toBe("false");
	});

	it("with values null the defaults show", () => {
		const store = makeStore(null);
		render(ImageViewerCard, { store });

		const slider = screen.getByLabelText("Backdrop strength") as HTMLInputElement;
		expect(slider.value).toBe("60");

		expect(screen.getByRole("switch", { name: "Show backdrop in wall overlay" }).getAttribute("aria-checked")).toBe("true");
		expect(screen.getByRole("switch", { name: "Show backdrop on item page" }).getAttribute("aria-checked")).toBe("true");
		expect(screen.getByRole("switch", { name: "Show backdrop in lightbox" }).getAttribute("aria-checked")).toBe("true");
	});

	it("preview backdrop present at default strength, gone after slider set to 0", async () => {
		const store = await makeRealStore({
			backdrop_strength: BACKDROP_DEFAULTS.strength,
			backdrop_wall: BACKDROP_DEFAULTS.wall,
			backdrop_item: BACKDROP_DEFAULTS.item,
			backdrop_lightbox: BACKDROP_DEFAULTS.lightbox,
		});
		render(ImageViewerCard, { store });

		expect(screen.queryByTestId("backdrop")).not.toBeNull();

		const slider = screen.getByLabelText("Backdrop strength");
		await fireEvent.input(slider, { target: { value: "0" } });

		expect(screen.queryByTestId("backdrop")).toBeNull();
	});
});
