/* global console */
// trash-shots.mjs — Playwright screenshots for /trash page
// Vite: http://127.0.0.1:5183 · Backend fixture: :8010

import { chromium } from 'playwright';
import { mkdirSync } from 'node:fs';

const out = process.argv[2] || 'shots/trash';
mkdirSync(out, { recursive: true });

const errors = [];
const sizes = {};
const BASE = 'http://127.0.0.1:5183';

const browser = await chromium.launch();

async function shot(page, name, w, h) {
  await page.waitForTimeout(700);
  await page.screenshot({ path: `${out}/trash-${name}-${w}x${h}.png` });
}

async function hitTest(locator, label) {
  const box = await locator.boundingBox();
  if (!box) return;
  sizes[label] = { width: box.width, height: box.height };
  if (box.width < 44 || box.height < 44) {
    errors.push(`${label}: ${box.width}x${box.height} < 44`);
  }
}

// Run one size per fresh backend (Empty deletes the fixture items): node trash-shots.mjs <out> <width>
const only = process.argv[3];
for (const [w, h] of [[1440, 900], [390, 844]].filter(([sw]) => !only || String(sw) === only)) {
  const page = await browser.newPage({ viewport: { width: w, height: h } });

  // --- empty state ---
  await page.goto(`${BASE}/trash`);
  await shot(page, 'empty', w, h);

  // --- fill trash via API ---
  for (const id of ['3', '4', '5']) {
    try {
      await page.request.delete(`${BASE}/api/library/images/${id}`);
    } catch { /* ignore */ }
  }

  // --- filled state ---
  await page.goto(`${BASE}/trash`);
  await shot(page, 'filled', w, h);

  const emptyBtn = page.getByRole('button', { name: /Empty trash/ });
  const restoreBtn = page.getByRole('button', { name: /^Restore/ }).first();
  const cancelBtn = page.getByRole('button', { name: 'Cancel' });
  const confirmBtn = page.getByRole('button', { name: 'Confirm' });

  // Hit-test Restore (visible in filled state)
  await hitTest(restoreBtn, `Restore ${w}x${h}`);

  // --- open confirm dialog (no force → Playwright hit-tests internally) ---
  await hitTest(emptyBtn, `Empty trash ${w}x${h}`);
  await emptyBtn.click();
  await shot(page, 'confirm', w, h);

  // Hit-test dialog buttons while visible
  await hitTest(cancelBtn, `Cancel ${w}x${h}`);
  await hitTest(confirmBtn, `Confirm ${w}x${h}`);

  // --- cancel, then restore first row ---
  await cancelBtn.click();
  await restoreBtn.click();
  await shot(page, 'restored', w, h);

  // --- empty for real ---
  await emptyBtn.click();
  await confirmBtn.click();
  await shot(page, 'emptied', w, h);

  await page.close();
}

await browser.close();
console.log(JSON.stringify({ errors, sizes }));
