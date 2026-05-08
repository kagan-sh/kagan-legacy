import { mkdtempSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { defineConfig, devices } from '@playwright/test';

/**
 * E2E test isolation strategy:
 *
 * 1. A fresh temp directory with a throwaway SQLite DB is created per run.
 * 2. `uv run poe web-build && uv run kagan web --db <temp>/kagan.db --no-open --port 8766`
 *    refreshes the bundled SPA and starts a sandboxed server with auth skipped
 *    (`web_ui` mode).
 * 3. Tests hit ONLY the sandboxed server — zero production data contact.
 * 4. The temp directory is cleaned up by global-teardown.ts.
 *
 * When BASE_URL is explicitly set, the webServer is skipped (CI may provision
 * its own isolated server). The caller is then responsible for isolation.
 */

const useExternalServer = Boolean(process.env.BASE_URL);
const E2E_PORT = 8766;
const E2E_BASE = `http://127.0.0.1:${E2E_PORT}`;
const tempDir = useExternalServer ? '' : mkdtempSync(join(tmpdir(), 'kagan-e2e-'));
const dbPath = useExternalServer ? '' : join(tempDir, 'kagan.db');

export default defineConfig({
  testDir: './e2e',
  // temp dir created inline above; no globalSetup needed.
  globalTeardown: useExternalServer ? undefined : './e2e/global-teardown.ts',
  reporter: 'list',
  workers: 1,

  use: {
    baseURL: process.env.BASE_URL || E2E_BASE,
    trace: 'on-first-retry',
    screenshot: 'only-on-failure',
  },

  // Spin up an isolated Kagan web server with a throwaway DB.
  // Requires web bundle (`pnpm run build`). Auth is auto-skipped in web_ui mode.
  ...(useExternalServer
    ? {}
    : {
        webServer: {
          // KAGAN_FAKE_AGENT=1 registers a deterministic fake-agent backend so
          // E2E tests can drive tasks to RUNNING state without a real agent.
          // The flag is safe to pass unconditionally — the server ignores it
          // when the eng-core fake-agent feature is not yet compiled in.
          command: `uv run poe web-build && uv run kagan web --db "${dbPath}" --no-open --port ${E2E_PORT}`,
          port: E2E_PORT,
          reuseExistingServer: false,
          timeout: 30_000,
          env: {
            KAGAN_E2E_TEMP_DIR: tempDir,
            KAGAN_FAKE_AGENT: '1',
          },
        },
      }),

  projects: [
    {
      name: 'chromium',
      use: { ...devices['Desktop Chrome'] },
    },
  ],
});
