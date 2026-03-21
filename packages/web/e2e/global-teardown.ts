/**
 * Playwright global teardown — removes the temp directory created by global-setup.ts.
 */
import { rmSync } from 'node:fs';

export default function globalTeardown() {
  const tempDir = process.env.KAGAN_E2E_TEMP_DIR;
  if (tempDir) {
    try {
      rmSync(tempDir, { recursive: true, force: true });
    } catch {
      // Best-effort cleanup; CI runners clean /tmp anyway.
    }
  }
}
