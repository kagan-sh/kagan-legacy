/**
 * Extended Playwright test fixture that collects Istanbul coverage from
 * vite-plugin-istanbul-instrumented builds. Tests should import `test`
 * from this file instead of `@playwright/test` when coverage is desired.
 *
 * Usage in spec files:
 *   import { test, expect } from './coverage-fixture';
 */
import { test as base, expect } from '@playwright/test';
import * as fs from 'node:fs';
import * as path from 'node:path';

const NYC_OUTPUT = path.join(process.cwd(), '.nyc_output');

export const test = base.extend({
  page: async ({ page }, use) => {
    await use(page);

    if (process.env.E2E_COVERAGE !== '1') return;

    const coverage = await page.evaluate(() => {
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      return (window as any).__coverage__ ?? null;
    });

    if (coverage) {
      fs.mkdirSync(NYC_OUTPUT, { recursive: true });
      const outFile = path.join(
        NYC_OUTPUT,
        `playwright-${Date.now()}-${Math.random().toString(36).slice(2)}.json`
      );
      fs.writeFileSync(outFile, JSON.stringify(coverage));
    }
  },
});

export { expect };
