// Pixel diff of two PNG folders: node diff.mjs <before> <after> name...  (prints differing pixel counts)
import { chromium } from "@playwright/test";
import { readFileSync } from "node:fs";
import process from "node:process";

const [a, b, ...names] = process.argv.slice(2);
const browser = await chromium.launch();
const page = await browser.newPage();
for (const n of names) {
  const urls = [a, b].map((d) => "data:image/png;base64," + readFileSync(`${d}/${n}.png`).toString("base64"));
  const diff = await page.evaluate(async (u) => {
    const load = (s) => new Promise((r) => { const i = new Image(); i.onload = () => r(i); i.src = s; });
    const [x, y] = await Promise.all(u.map(load));
    if (x.width !== y.width || x.height !== y.height) return "size";
    const px = (i) => { const c = document.createElement("canvas"); c.width = i.width; c.height = i.height; const g = c.getContext("2d"); g.drawImage(i, 0, 0); return g.getImageData(0, 0, i.width, i.height).data; };
    const p = px(x), q = px(y); let n = 0;
    for (let k = 0; k < p.length; k += 4) if (p[k] !== q[k] || p[k + 1] !== q[k + 1] || p[k + 2] !== q[k + 2]) n++;
    return n;
  }, urls);
  console.log(n, diff);
}
await browser.close();
