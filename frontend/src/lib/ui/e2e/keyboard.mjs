/* global document, console */
// Keyboard check on /__ui: Popover and DropdownMenu keep Escape, outside tap, arrows, Home, End.
// Needs the stub (:8010) and `vite --config vite.stub.config.ts` (:5183). Exit 1 on a failed check.
import { chromium } from "@playwright/test";
import process from "node:process";

const browser = await chromium.launch();
let failed = 0;
const check = (name, ok, got) => { if (!ok) failed++; console.log(`${ok ? "PASS" : "FAIL"} ${name}${ok ? "" : ` (got ${got})`}`); };

const page = await browser.newPage({ viewport: { width: 1440, height: 900 } });
await page.goto("http://127.0.0.1:5183/__ui");
await page.waitForSelector(".ui-root h1");
await page.waitForTimeout(500);

const pop = page.getByRole("button", { name: "Popover", exact: true });
const content = page.getByText("Popover content");
const focusedLabel = () => page.evaluate(() => document.activeElement?.getAttribute("aria-label") ?? document.activeElement?.textContent?.trim());

await pop.click();
check("Popover opens on click", await content.isVisible(), "hidden");
await page.keyboard.press("Escape");
await page.waitForTimeout(200);
check("Popover: Escape closes", !(await content.isVisible()), "still open");
check("Popover: focus returns to trigger after Escape", (await focusedLabel()) === "Popover", await focusedLabel());

await pop.click();
await page.mouse.click(1300, 600);
await page.waitForTimeout(200);
check("Popover: outside tap closes", !(await content.isVisible()), "still open");

const menuBtn = page.getByRole("button", { name: /^Sort/ });
const items = page.getByRole("menuitemradio");
const active = () => page.evaluate(() => document.activeElement?.textContent?.trim());
await menuBtn.focus();
await page.keyboard.press("Enter");
await page.waitForTimeout(200);
check("Dropdown: Enter opens, 3 items", (await items.count()) === 3, await items.count());
await page.keyboard.press("ArrowDown");
const first = await active();
await page.keyboard.press("ArrowDown");
const second = await active();
check("Dropdown: ArrowDown moves to the next item", first !== second && !!second, `${first} -> ${second}`);
await page.keyboard.press("ArrowUp");
check("Dropdown: ArrowUp moves back", (await active()) === first, await active());
await page.keyboard.press("End");
check("Dropdown: End goes to last item", (await active()) === "Random", await active());
await page.keyboard.press("Home");
check("Dropdown: Home goes to first item", (await active()) === "Newest", await active());
await page.keyboard.press("Escape");
await page.waitForTimeout(200);
check("Dropdown: Escape closes", (await items.count()) === 0, await items.count());
check("Dropdown: focus returns to trigger", (await focusedLabel())?.startsWith("Sort"), await focusedLabel());

await browser.close();
process.exit(failed ? 1 : 0);
