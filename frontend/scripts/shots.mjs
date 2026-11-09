// Screenshots only, no assertions. Needs the stub on :8000 and Vite on :2900.
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";

import process from "node:process";
const out = process.argv[2] ?? "shots";
mkdirSync(out, { recursive: true });
const pages = [
  ["search", "/"],
  ["search-q", "/?q=sunset"],
  ["library", "/library"],
  ["see-all-images", "/library/stash/images"],
  ["see-all-web", "/see-all?source=danbooru&q=sunset"],
];
const widths = [1440, 1024, 768];

const browser = await chromium.launch();
for (const w of widths) {
  const page = await browser.newPage({ viewport: { width: w, height: 900 } });
  for (const [name, path] of pages) {
    await page.goto("http://127.0.0.1:2900" + path);
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${out}/${name}-${w}.png` });
  }
  await page.close();
}
await browser.close();
