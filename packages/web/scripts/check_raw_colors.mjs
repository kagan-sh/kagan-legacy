#!/usr/bin/env node
/**
 * Baseline audit: scan the web package for raw Tailwind color classes
 * (`text-red-500`, `bg-blue-400`, `border-green-700`, etc.) that should
 * be driven by CSS custom properties instead.
 *
 * Never fails the build — prints a count so future PRs can track drift.
 */
import { readFile, readdir } from 'node:fs/promises';
import { join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = fileURLToPath(new URL('../src', import.meta.url));
const EXTS = new Set(['.ts', '.tsx', '.css']);
const IGNORE = new Set(['node_modules', 'dist', 'e2e', 'public']);

// Tailwind color palette tokens we want to discourage in favor of CSS vars.
// Excludes: white, black, transparent, current, inherit, auto (they aren't palette colors).
const COLOR_NAMES = [
  'slate', 'gray', 'zinc', 'neutral', 'stone',
  'red', 'orange', 'amber', 'yellow', 'lime',
  'green', 'emerald', 'teal', 'cyan', 'sky',
  'blue', 'indigo', 'violet', 'purple', 'fuchsia',
  'pink', 'rose',
];
const UTILITIES = ['text', 'bg', 'border', 'ring', 'from', 'to', 'via', 'fill', 'stroke', 'placeholder', 'decoration', 'outline', 'shadow', 'divide', 'accent', 'caret'];

const RE = new RegExp(
  `\\b(?:${UTILITIES.join('|')})-(?:${COLOR_NAMES.join('|')})-(?:50|100|200|300|400|500|600|700|800|900|950)\\b`,
  'g',
);

async function* walk(dir) {
  for (const entry of await readdir(dir, { withFileTypes: true })) {
    if (IGNORE.has(entry.name)) continue;
    const full = join(dir, entry.name);
    if (entry.isDirectory()) {
      yield* walk(full);
    } else if (entry.isFile()) {
      const idx = entry.name.lastIndexOf('.');
      if (idx >= 0 && EXTS.has(entry.name.slice(idx))) yield full;
    }
  }
}

const hits = new Map();
let total = 0;

for await (const file of walk(ROOT)) {
  const text = await readFile(file, 'utf8');
  const matches = text.match(RE);
  if (!matches) continue;
  hits.set(relative(ROOT, file), matches.length);
  total += matches.length;
}

const sorted = [...hits.entries()].sort((a, b) => b[1] - a[1]);

console.log(`Raw Tailwind color audit — ${total} hit(s) across ${hits.size} file(s)`);
if (sorted.length > 0) {
  console.log('');
  console.log('Top offenders:');
  for (const [file, count] of sorted.slice(0, 20)) {
    console.log(`  ${count.toString().padStart(4)}  ${file}`);
  }
}

// Baseline only — always exit 0.
process.exit(0);
