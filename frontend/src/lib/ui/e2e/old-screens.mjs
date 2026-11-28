// Discover and Queue screenshots of one Vite origin: node old-screens.mjs <port> <out-dir>
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import process from "node:process";

const [port, out] = [process.argv[2], process.argv[3]];
mkdirSync(out, { recursive: true });
const browser = await chromium.launch();
for (const w of [1440, 390]) {
  const page = await browser.newPage({ viewport: { width: w, height: 900 } });
  for (const [name, path] of [["discover", "/"], ["queue", "/queue"]]) {
    await page.goto(`http://127.0.0.1:${port}${path}`);
    await page.waitForTimeout(2500);
    await page.screenshot({ path: `${out}/${name}-${w}.png` });
  }
  await page.close();
}
await browser.close();
