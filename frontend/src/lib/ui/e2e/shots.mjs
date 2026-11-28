// Screenshots of /__ui (dark, light; 1440 and 390 px) plus Discover and Queue. Needs stub :8010 and vite --config vite.stub.config.ts :5183.
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import process from "node:process";

const out = process.argv[2] ?? "shots-ui";
mkdirSync(out, { recursive: true });
const base = "http://127.0.0.1:5183";
const browser = await chromium.launch();
for (const w of [1440, 390]) {
  const page = await browser.newPage({ viewport: { width: w, height: 900 } });
  for (const theme of ["dark", "light"]) {
    await page.goto(base + "/__ui");
    await page.waitForTimeout(2500);
    if (theme === "light") await page.getByRole("button", { name: /^Theme/ }).click();
    await page.waitForTimeout(300);
    await page.screenshot({ path: `${out}/ui-${theme}-${w}.png`, fullPage: true });
  }
  for (const [name, path] of [["discover", "/"], ["queue", "/queue"]]) {
    await page.goto(base + path);
    await page.waitForTimeout(1500);
    await page.screenshot({ path: `${out}/${name}-${w}.png` });
  }
  await page.close();
}
await browser.close();
