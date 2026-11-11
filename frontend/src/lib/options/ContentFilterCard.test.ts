// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, cleanup } from "@testing-library/svelte";
import ContentFilterCard from "./ContentFilterCard.svelte";
import type { OptionsStore } from "../stores/options.svelte";

vi.mock("../stores/options.svelte", () => ({
	options: { values: null, set: vi.fn() },
}));

function makeStore(values: Record<string, unknown> | null) {
	return { values, set: vi.fn() } as unknown as OptionsStore & { set: ReturnType<typeof vi.fn> };
}

afterEach(() => cleanup());

describe("ContentFilterCard", () => {
	it("values null: switch is off", () => {
		render(ContentFilterCard, { store: makeStore(null) });
		expect(screen.getByRole("switch", { name: "Allow blurred tags in safe mode" }).getAttribute("aria-checked")).toBe("false");
	});

	it("reflects the stored value", () => {
		render(ContentFilterCard, { store: makeStore({ allow_blurred_tags: true }) });
		expect(screen.getByRole("switch", { name: "Allow blurred tags in safe mode" }).getAttribute("aria-checked")).toBe("true");
	});

	it("click sends the flipped value", async () => {
		const store = makeStore({ allow_blurred_tags: false });
		render(ContentFilterCard, { store });
		await fireEvent.click(screen.getByRole("switch", { name: "Allow blurred tags in safe mode" }));
		expect(store.set).toHaveBeenCalledWith({ allow_blurred_tags: true });
	});
});
