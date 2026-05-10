import { test, expect } from "./coverage-fixture";
import { ensureBoardReady } from "./helpers";

test.describe("Spotlight", () => {
  test.beforeEach(async ({ page, request }) => {
    await ensureBoardReady(page, request);
  });

  test("opens via Cmd/Ctrl+K and closes with Escape", async ({ page }) => {
    const isMac = await page.evaluate(() =>
      navigator.platform.toLowerCase().includes("mac"),
    );
    await page.keyboard.press(isMac ? "Meta+k" : "Control+k");

    const dialog = page.getByRole("dialog", { name: /command palette/i });
    await expect(dialog).toBeVisible();

    await page.keyboard.press("Escape");
    await expect(dialog).toBeHidden();
  });

  test("opens via header search trigger", async ({ page }) => {
    await page.getByRole("button", { name: /search tasks/i }).click();
    const dialog = page.getByRole("dialog", { name: /command palette/i });
    await expect(dialog).toBeVisible();
  });

  test("filters tasks by query", async ({ page }) => {
    await page.getByRole("button", { name: /search tasks/i }).click();
    const dialog = page.getByRole("dialog", { name: /command palette/i });
    const input = dialog.getByPlaceholder(/search tasks, run commands/i);
    await input.fill("zzz-no-such-task");
    await expect(dialog.getByText(/no results/i)).toBeVisible();
  });
});
