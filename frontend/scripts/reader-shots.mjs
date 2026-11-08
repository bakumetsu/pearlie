/* global console */
// Reader screenshots, no assertions. Stub on :8010, Vite (vite.stub.config.ts) on :5183.
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import process from "node:process";

const out = process.argv[2] ?? "shots";
mkdirSync(out, { recursive: true });
const sizes = [[1440, 900], [1024, 768], [768, 1024], [1080, 1920]];
const browser = await chromium.launch();
const errors = [];
for (const [w, h] of sizes) {
  const page = await browser.newPage({ viewport: { width: w, height: h } });
  page.on("pageerror", (e) => errors.push(String(e)));
  page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });
  const shot = async (name) => { await page.waitForTimeout(700); await page.screenshot({ path: `${out}/${name}-${w}x${h}.png` }); };
  await page.goto("http://127.0.0.1:5183/read/0");
  await page.waitForTimeout(1500);
  await shot("reader");
  await page.keyboard.press("t"); await shot("thumbs"); await page.keyboard.press("t");
  await page.keyboard.press("?"); await shot("help"); await page.keyboard.press("Escape");
  await page.keyboard.press("End"); await page.keyboard.press("ArrowRight"); await page.keyboard.press("ArrowRight"); await shot("endcard");
  await page.close();
}
console.log(JSON.stringify({ errors }));
await browser.close();
