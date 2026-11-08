/* global document, console */
// Item/player screenshots and the cross-route playback check. Stub on :8010, Vite (vite.stub.config.ts) on :5183.
import { chromium } from "@playwright/test";
import { mkdirSync } from "node:fs";
import process from "node:process";

const out = process.argv[2] ?? "shots";
mkdirSync(out, { recursive: true });
const base = "http://127.0.0.1:5183";
const browser = await chromium.launch({ args: ["--autoplay-policy=no-user-gesture-required"] });
const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
const errors = [];
page.on("pageerror", (e) => errors.push(String(e)));
page.on("console", (m) => { if (m.type() === "error") errors.push(m.text()); });

const shot = async (name) => { await page.waitForTimeout(1200); await page.screenshot({ path: `${out}/${name}.png` }); };

await page.goto(`${base}/item/images/0`); await shot("item-image");
await page.goto(`${base}/item/series/0`); await shot("item-series");
await page.goto(`${base}/item/videos/0`); await shot("item-video");

await page.getByRole("button", { name: "Play" }).first().click();
await page.waitForTimeout(1500);
const t1 = await page.evaluate(() => document.querySelector("video")?.currentTime ?? -1);
await shot("item-video-playing");

// client-side navigation: use the nav link so the SPA does not reload
await page.getByRole("link", { name: /library/i }).first().click();
await page.waitForTimeout(1500);
const t2 = await page.evaluate(() => { const v = document.querySelector("video"); return v ? { t: v.currentTime, paused: v.paused } : null; });
await shot("mini-docked");
console.log(JSON.stringify({ t1, afterNav: t2, url: page.url(), errors }));
await browser.close();
