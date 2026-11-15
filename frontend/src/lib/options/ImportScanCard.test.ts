// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from "vitest";
import { render, screen, fireEvent, waitFor, cleanup } from "@testing-library/svelte";
import ImportScanCard from "./ImportScanCard.svelte";
import type { Api } from "../api/client";

afterEach(cleanup);

describe("ImportScanCard", () => {
	it("scans and shows the counts", async () => {
		const api = {
			scanRule34: vi.fn().mockResolvedValue({ found: 5, imported: 3, skipped: 2 }),
		} as unknown as Api;
		render(ImportScanCard, { api });
		await fireEvent.click(screen.getByTestId("import-scan"));
		await waitFor(() => expect(screen.getByTestId("import-result")).toBeDefined());
		expect(screen.getByTestId("import-result").textContent).toContain("5 files found, 3 new, 2 skipped");
		expect(api.scanRule34).toHaveBeenCalledTimes(1);
	});

	it("shows an error when the scan fails", async () => {
		const api = { scanRule34: vi.fn().mockRejectedValue(new Error("x")) } as unknown as Api;
		render(ImportScanCard, { api });
		await fireEvent.click(screen.getByTestId("import-scan"));
		await waitFor(() => expect(screen.getByRole("alert")).toBeDefined());
	});
});
