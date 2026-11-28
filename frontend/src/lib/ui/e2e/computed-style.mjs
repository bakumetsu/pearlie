/* global document, console, getComputedStyle */
// Computed-style check on /__ui (stub :8010, vite --config vite.stub.config.ts :5183). Exit 1 on a failed check.
import { chromium } from "@playwright/test";
import process from "node:process";

const browser = await chromium.launch();
let failed = 0;
const check = (name, ok, got) => { if (!ok) failed++; console.log(`${ok ? "PASS" : "FAIL"} ${name}${ok ? "" : ` (got ${got})`}`); };

for (const w of [1440, 390]) {
  const page = await browser.newPage({ viewport: { width: w, height: 900 } });
  await page.goto("http://127.0.0.1:5183/__ui");
  await page.waitForSelector(".ui-root h1");
  await page.waitForTimeout(800);
  // Touch rule: every visible button, input, select, tab, radio under .ui-root is at least 44 px high (checkbox row, slider, textarea excluded by role).
  const small = await page.evaluate(() =>
    [...document.querySelectorAll(".ui-root button, .ui-root input:not([type=checkbox]):not([type=range]), .ui-root select, .ui-root [role=tab], .ui-root [role=radio], .ui-root [role=switch]")]
      .filter((e) => e.getBoundingClientRect().width > 0)
      .map((e) => ({ t: e.tagName + (e.getAttribute("aria-label") ?? e.textContent ?? "").slice(0, 20), h: e.getBoundingClientRect().height }))
      .filter((e) => e.h < 43.5),
  );
  check(`${w}px: all controls >= 44 px high`, small.length === 0, JSON.stringify(small));

  const s = await page.evaluate(() => {
    const cs = (sel) => getComputedStyle(document.querySelector(sel));
    const root = cs(".ui-root");
    const btn = [...document.querySelectorAll(".ui-root button")].find((b) => b.textContent.trim() === "Save");
    const bs = getComputedStyle(btn);
    const fgTok = getComputedStyle(btn).getPropertyValue("--primary-foreground").trim();
    const input = cs(".ui-root input[aria-label=Input]");
    return { fgTok, btnColor: bs.color, btnWeight: bs.fontWeight, bg: root.backgroundColor, btnBg: bs.backgroundColor, btnRadius: bs.borderRadius, btnH: bs.height, inRadius: input.borderRadius, pillRadius: cs(".ui-root input[aria-label=\"Pill input\"]").borderRadius, font: root.fontFamily };
  });
  check(`${w}px: Button radius 6px or 8px`, ["6px", "8px"].includes(s.btnRadius), s.btnRadius);
  check(`${w}px: Button height 44px`, s.btnH === "44px", s.btnH);
  check(`${w}px: Input radius 8px`, s.inRadius === "8px", s.inRadius);
  check(`${w}px: Input shape=pill is a pill`, parseFloat(s.pillRadius) >= 22, s.pillRadius);
  check(`${w}px: Primary button uses --primary token`, s.btnBg !== s.bg && s.btnBg !== "rgba(0, 0, 0, 0)", s.btnBg);
  check(`${w}px: Primary text uses --primary-foreground, weight 600`, s.btnColor === s.fgTok && s.btnWeight === "600", s.btnColor + " " + s.btnWeight);
  check(`${w}px: Inter font`, /Inter/.test(s.font), s.font);
  await page.close();
}
await browser.close();
process.exit(failed ? 1 : 0);
