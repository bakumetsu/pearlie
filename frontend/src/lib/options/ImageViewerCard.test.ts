// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/svelte";
import ImageViewerCard from "./ImageViewerCard.svelte";
import { BACKDROP_DEFAULTS } from "./backdrop";
import type { OptionsStore } from "../stores/options.svelte";

vi.mock("../stores/options.svelte", () => ({
	options: { values: null, set: vi.fn() },
}));

function makeStore(values: Record<string, unknown> | null) {
	return { values, set: vi.fn() } as unknown as OptionsStore & { set: ReturnType<typeof vi.fn> };
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
		const store = makeStore({
			backdrop_strength: BACKDROP_DEFAULTS.strength,
			backdrop_wall: true,
			backdrop_item: true,
			backdrop_lightbox: true,
		});
		render(ImageViewerCard, { store });

		const wall = screen.getByRole("switch", { name: "Wall overlay" });
		expect(wall.getAttribute("aria-checked")).toBe("true");
		await fireEvent.click(wall);
		expect(store.set).toHaveBeenCalledWith({ backdrop_wall: false });
		expect(wall.getAttribute("aria-checked")).toBe("false");

		const item = screen.getByRole("switch", { name: "Item page" });
		expect(item.getAttribute("aria-checked")).toBe("true");
		await fireEvent.click(item);
		expect(store.set).toHaveBeenCalledWith({ backdrop_item: false });
		expect(item.getAttribute("aria-checked")).toBe("false");

		const lightbox = screen.getByRole("switch", { name: "Lightbox" });
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

		expect(screen.getByRole("switch", { name: "Wall overlay" }).getAttribute("aria-checked")).toBe("true");
		expect(screen.getByRole("switch", { name: "Item page" }).getAttribute("aria-checked")).toBe("true");
		expect(screen.getByRole("switch", { name: "Lightbox" }).getAttribute("aria-checked")).toBe("true");
	});

	it("preview backdrop present at default strength, gone after slider set to 0", async () => {
		const store = makeStore({
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
