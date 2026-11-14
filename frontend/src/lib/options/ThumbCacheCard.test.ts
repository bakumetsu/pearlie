// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/svelte";
import ThumbCacheCard from "./ThumbCacheCard.svelte";
import { createOptions } from "../stores/options.svelte";
import type { Api } from "../api/client";

const defaultBase = {
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
	trash_retention_days: 7,
	source_pace: {},
	thumb_cache: { max_mb: 1024, used_mb: 12.4, files: 30, available: true },
};

function makeStore(thumbCacheOverrides: Record<string, unknown> = {}) {
	const base = {
		...defaultBase,
		thumb_cache: { ...defaultBase.thumb_cache, ...thumbCacheOverrides },
	};
	const putOptions = vi.fn((body: Record<string, unknown>) =>
		Promise.resolve({ ...base, ...body })
	);
	const getOptions = vi.fn().mockResolvedValue(base);
	const store = createOptions({
		sfw: { set: vi.fn() },
		player: { loadRate: vi.fn() },
		storage: { getItem: () => null, removeItem: () => {} },
		debounceMs: 0,
	});
	return { store, putOptions, getOptions, base };
}

async function renderCard(thumbCacheOverrides: Record<string, unknown> = {}) {
	const { store, putOptions, getOptions } = makeStore(thumbCacheOverrides);
	await store.load({ getOptions, putOptions } as unknown as Api);
	const api = {
		clearThumbCache: vi.fn().mockResolvedValue({ freed_mb: 12 }),
	} as unknown as Api;
	const result = render(ThumbCacheCard, { store, api });
	return { ...result, api, putOptions };
}

afterEach(() => {
	cleanup();
	vi.useRealTimers();
	vi.clearAllMocks();
});

describe("ThumbCacheCard", () => {
	it("(a) shows usage text", async () => {
		await renderCard();
		expect(screen.getByText("12.4 MB of 1 GB used")).toBeTruthy();
	});

	it("(b) shows 'Near the limit' at 950/1024 but not at 100/1024", async () => {
		await renderCard({ used_mb: 950 });
		expect(screen.getByText("Near the limit")).toBeTruthy();
		cleanup();

		await renderCard({ used_mb: 100 });
		expect(screen.queryByText("Near the limit")).toBeNull();
	});

	it("(c) valid cap 2048 on change calls putOptions", async () => {
		const { putOptions } = await renderCard();
		const input = screen.getByTestId("thumb-cache-cap") as HTMLInputElement;
		input.value = "2048";
		await fireEvent.change(input);
		await waitFor(() => {
			expect(putOptions).toHaveBeenCalledWith({ thumb_cache_max_mb: 2048 });
		});
	});

	it("(h) click Increase size limit increments cap by 1", async () => {
		const { putOptions } = await renderCard();
		const btn = screen.getByRole("button", { name: "Increase size limit" });
		await fireEvent.click(btn);
		await waitFor(() => {
			expect(putOptions).toHaveBeenCalledWith({ thumb_cache_max_mb: 1025 });
		});
	});

	it("(i) click Decrease size limit decrements cap by 1", async () => {
		const { putOptions } = await renderCard();
		const btn = screen.getByRole("button", { name: "Decrease size limit" });
		await fireEvent.click(btn);
		await waitFor(() => {
			expect(putOptions).toHaveBeenCalledWith({ thumb_cache_max_mb: 1023 });
		});
	});

	it("(j) at max 20480, Increase size limit does not call putOptions", async () => {
		const { putOptions } = await renderCard({ max_mb: 20480 });
		const btn = screen.getByRole("button", { name: "Increase size limit" });
		await fireEvent.click(btn);
		expect(putOptions).not.toHaveBeenCalled();
	});

	it("(d) invalid caps show alert and do not call putOptions", async () => {
		const { putOptions } = await renderCard();
		const input = screen.getByTestId("thumb-cache-cap") as HTMLInputElement;

		input.value = "10";
		await fireEvent.change(input);
		const alert1 = await screen.findByRole("alert");
		expect(alert1.textContent).toBe("Enter a whole number from 50 to 20480");
		expect(putOptions).not.toHaveBeenCalled();
		cleanup();

		const { putOptions: put2 } = await renderCard();
		const input2 = screen.getByTestId("thumb-cache-cap") as HTMLInputElement;
		input2.value = "1.5";
		await fireEvent.change(input2);
		const alert2 = await screen.findByRole("alert");
		expect(alert2.textContent).toBe("Enter a whole number from 50 to 20480");
		expect(put2).not.toHaveBeenCalled();
		cleanup();

		const { putOptions: put3 } = await renderCard();
		const input3 = screen.getByTestId("thumb-cache-cap") as HTMLInputElement;
		input3.value = "";
		await fireEvent.change(input3);
		const alert3 = await screen.findByRole("alert");
		expect(alert3.textContent).toBe("Enter a whole number from 50 to 20480");
		expect(put3).not.toHaveBeenCalled();
	});

	it("(e) Clear needs two taps", async () => {
		const { api } = await renderCard();
		const btn = screen.getByTestId("thumb-cache-clear") as HTMLButtonElement;

		await fireEvent.click(btn);
		expect(api.clearThumbCache).not.toHaveBeenCalled();
		await screen.findByText("Tap again to clear");
		expect(btn.getAttribute("aria-label")).toBe("Tap again to clear");

		await fireEvent.click(btn);
		expect(api.clearThumbCache).toHaveBeenCalledTimes(1);

		await waitFor(() => {
			expect(screen.getByText("0 MB of 1 GB used")).toBeTruthy();
		});
	});

	it("(f) Escape cancels confirming state", async () => {
		const { api } = await renderCard();
		const btn = screen.getByTestId("thumb-cache-clear") as HTMLButtonElement;

		await fireEvent.click(btn);
		await screen.findByText("Tap again to clear");

		await fireEvent.keyDown(btn, { key: "Escape" });

		expect(api.clearThumbCache).not.toHaveBeenCalled();
		expect(btn.getAttribute("aria-label")).toBe("Clear thumbnail cache");
		expect(screen.queryByText("Tap again to clear")).toBeNull();
	});

	it("(g) Clear disabled with 'Cache is empty' when used 0 and files 0", async () => {
		await renderCard({ used_mb: 0, files: 0 });
		const btn = screen.getByTestId("thumb-cache-clear") as HTMLButtonElement;
		expect(btn.disabled).toBe(true);
		expect(btn.getAttribute("title")).toBe("Cache is empty");
	});

	it("(g) Clear disabled with 'Cache unavailable' when available is false", async () => {
		await renderCard({ available: false });
		const btn = screen.getByTestId("thumb-cache-clear") as HTMLButtonElement;
		expect(btn.disabled).toBe(true);
		expect(btn.getAttribute("title")).toBe("Cache unavailable");
	});
});
