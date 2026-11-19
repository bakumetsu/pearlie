// Renders the PNG icons from the SVG sources in public/. Run: node scripts/render-icons.mjs [outDir]
import { chromium } from "@playwright/test";
import { readFileSync, mkdirSync } from "node:fs";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import process from "node:process";

const root = join(dirname(fileURLToPath(import.meta.url)), "..", "public");
const out = process.argv[2] ?? root;
mkdirSync(out, { recursive: true });

// [source svg, file name, size]; 16 and 32 are previews for the legibility check.
const jobs = [
  ["icon-maskable.svg", "apple-touch-icon.png", 180],
  ["icon.svg", "icon-192.png", 192],
  ["icon.svg", "icon-512.png", 512],
  ["icon-maskable.svg", "icon-maskable-512.png", 512],
];
if (process.argv[2]) {
  jobs.push(["icon.svg", "preview-16.png", 16], ["icon.svg", "preview-32.png", 32]);
}

const browser = await chromium.launch();
for (const [src, name, size] of jobs) {
  const svg = readFileSync(join(root, src), "utf8");
  const page = await browser.newPage({ viewport: { width: size, height: size } });
  await page.setContent(
    `<style>html,body{margin:0;background:transparent}svg{display:block;width:${size}px;height:${size}px}</style>${svg}`,
  );
  await page.screenshot({ path: join(out, name), omitBackground: true });
  await page.close();
}
await browser.close();
