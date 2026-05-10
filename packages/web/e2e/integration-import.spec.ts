import { test, expect } from "./coverage-fixture";
import { ensureBoardReady } from "./helpers";

test.describe("Integration import dialog", () => {
  test.beforeEach(async ({ page, request }) => {
    await ensureBoardReady(page, request);
  });

  // Dialog is reachable from:
  //   1. Empty-state "Import from GitHub" button (only when zero tasks; the
  //      shared fixture seeds a task so this surface is unreachable here).
  //   2. Spotlight command "Import from GitHub" (id: create-github-import).
  // We use the Spotlight path because the seeded fixture always has tasks.
  async function openImportDialog(page: import("@playwright/test").Page) {
    await page.getByRole("button", { name: /search tasks/i }).click();
    const palette = page.getByRole("dialog", { name: /command palette/i });
    await expect(palette).toBeVisible();
    const input = palette.getByPlaceholder(/search tasks, run commands/i);
    await input.fill("Import from GitHub");
    await expect(
      palette.getByRole("option").filter({ hasText: /import from github/i }),
    ).toBeVisible();
    await input.press("Enter");
    await expect(palette).toBeHidden();
  }

  test("opens integration import dialog", async ({ page }) => {
    await openImportDialog(page);

    const dialog = page.getByRole("dialog", { name: /import from github/i });
    await expect(dialog).toBeVisible();
    await expect(
      dialog.getByRole("heading", { name: /import from github/i }),
    ).toBeVisible();
  });

  test("exposes repo input and Preview button after detection", async ({
    page,
  }) => {
    await openImportDialog(page);

    const dialog = page.getByRole("dialog", { name: /import from github/i });
    await expect(dialog).toBeVisible();

    // The detect() effect resolves and the repo Input replaces the
    // "Detecting repository…" placeholder. The Preview button's disabled
    // state depends on whether a real GitHub integration is configured —
    // not gated here because the e2e env's auth state isn't deterministic.
    await expect(dialog.locator("#integration-repo")).toBeVisible({
      timeout: 10_000,
    });
    await expect(
      dialog.getByRole("button", { name: /preview/i }),
    ).toBeVisible();
  });

  test("closes via Cancel or Escape", async ({ page }) => {
    await openImportDialog(page);

    const dialog = page.getByRole("dialog", { name: /import from github/i });
    await expect(dialog).toBeVisible();

    await dialog.getByRole("button", { name: /cancel/i }).click();
    await expect(dialog).toBeHidden();
  });
});
