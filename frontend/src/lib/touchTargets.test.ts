// frontend/src/lib/touchTargets.test.ts
import { describe, it, expect } from 'vitest';

const sources = import.meta.glob('/src/**/*.svelte', {
  query: '?raw',
  import: 'default',
  eager: true,
}) as Record<string, string>;

// ── helpers ──────────────────────────────────────────────────────────────────

function extractStyleBlock(source: string, filePath: string): string {
  const m = source.match(/<style[^>]*>([\s\S]*?)<\/style>/);
  if (!m) throw new Error(`No <style> block found in ${filePath}`);
  return m[1];
}

/**
 * Find the CSS rule whose selector line (after leading whitespace) starts with
 * the exact `selector` string, immediately followed by optional whitespace and
 * an opening `{`.  Returns the rule body (text between the outer braces).
 */
function findRuleBody(style: string, selector: string, filePath: string): string {
  const lines = style.split('\n');
  for (let i = 0; i < lines.length; i++) {
    const trimmed = lines[i].trimStart();
    if (!trimmed.startsWith(selector)) continue;

    // Ensure the next non-space char after the selector is '{' (not '.', '-', etc.)
    const after = trimmed.slice(selector.length);
    if (!/^\s*\{/.test(after)) continue;

    const braceIdx = lines[i].indexOf('{');
    let body = lines[i].slice(braceIdx + 1);
    let depth = 1;

    // Count braces on the opening line after '{'
    for (let k = braceIdx + 1; k < lines[i].length; k++) {
      if (lines[i][k] === '{') depth++;
      if (lines[i][k] === '}') depth--;
    }

    // Continue on subsequent lines until braces balance
    let j = i + 1;
    while (depth > 0 && j < lines.length) {
      body += '\n' + lines[j];
      for (const ch of lines[j]) {
        if (ch === '{') depth++;
        if (ch === '}') depth--;
      }
      j++;
    }

    return body;
  }
  throw new Error(`No rule found for selector "${selector}" in ${filePath}`);
}

/**
 * Return the pixel value of a CSS declaration, or null.
 * The negative look-behind prevents `min-height` from matching `height`.
 */
function getPx(body: string, prop: string): number | null {
  const re = new RegExp(`(?<![\\w-])${prop}\\s*:\\s*(\\d+(?:\\.\\d+)?)px`);
  const m = body.match(re);
  return m ? parseFloat(m[1]) : null;
}

function getMinPx(body: string, prop: string): number | null {
  const re = new RegExp(`min-${prop}\\s*:\\s*(\\d+(?:\\.\\d+)?)px`);
  const m = body.match(re);
  return m ? parseFloat(m[1]) : null;
}

function assertDimension(body: string, prop: string, label: string): void {
  const minVal = getMinPx(body, prop);
  const val = getPx(body, prop);
  const effective = Math.max(minVal ?? 0, val ?? 0);
  expect(
    effective,
    `${label}: ${prop} must be >= 44px (min-${prop}:${minVal ?? '–'}, ${prop}:${val ?? '–'})`,
  ).toBeGreaterThanOrEqual(44);
}

function getBody(file: string, selector: string): string {
  const source = sources[file];
  if (!source) throw new Error(`File not captured by glob: ${file}`);
  const style = extractStyleBlock(source, file);
  return findRuleBody(style, selector, file);
}

// ── targets ──────────────────────────────────────────────────────────────────

interface Target {
  file: string;
  selector: string;
  width: boolean; // width >= 44px also required
}

const targets: Target[] = [
  { file: '/src/routes/Item.svelte',      selector: '.bar-btn',         width: true },
  { file: '/src/lib/browse/Toolbar.svelte', selector: '.dd select',      width: false },
  { file: '/src/routes/Options.svelte',   selector: '.clear-btn',       width: true },
  { file: '/src/routes/Rules.svelte',     selector: '.tagchip button',  width: true },
  { file: '/src/routes/SeeAll.svelte',    selector: '.sort-select',     width: false },
  { file: '/src/routes/SeeAll.svelte',    selector: '.retry-btn',       width: false },
];

// ── tests ────────────────────────────────────────────────────────────────────

describe('touch target sizes (>= 44px)', () => {
  for (const t of targets) {
    describe(`${t.file} → ${t.selector}`, () => {
      it('height >= 44px', () => {
        const body = getBody(t.file, t.selector);
        assertDimension(body, 'height', t.selector);
      });

      if (t.width) {
        it('width >= 44px', () => {
          const body = getBody(t.file, t.selector);
          assertDimension(body, 'width', t.selector);
        });
      }
    });
  }
});
