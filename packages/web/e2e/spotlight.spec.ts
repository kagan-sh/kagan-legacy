import { test, expect } from "./coverage-fixture";
import { createTaskViaApi, ensureBoardReady } from "./helpers";

test.describe("Spotlight (command palette)", () => {
  test.beforeEach(async ({ page, request }) => {
    await ensureBoardReady(page, request);
  });

  test("closes with Escape after opening", async ({ page }) => {
    // Cmd+K is bound by two competing global handlers (shell-layout +
    // use-global-shortcuts) and opens both Spotlight and SessionPicker on the
    // same keypress, making the keyboard path racy. The header search button
    // is the only deterministic way to open just Spotlight.
    await page.getByRole("button", { name: /search tasks/i }).click();

    const dialog = page.getByRole("dialog", { name: /command palette/i });
    await expect(dialog).toBeVisible();

    // Escape handler lives on the input — press the key from there so we
    // don't depend on the rAF auto-focus winning the race.
    const input = dialog.getByPlaceholder(/search tasks, run commands/i);
    await input.press("Escape");
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

  test("Enter on a task result navigates to the task detail page", async ({
    page,
    request,
  }) => {
    const taskId = await createTaskViaApi(
      request,
      "Spotlight target xyz unique",
    );
    await page.goto("/board");

    await page.getByRole("button", { name: /search tasks/i }).click();
    const dialog = page.getByRole("dialog", { name: /command palette/i });
    const input = dialog.getByPlaceholder(/search tasks, run commands/i);
    await input.fill("Spotlight target xyz");

    await expect(
      dialog.getByRole("option").filter({ hasText: /spotlight target xyz/i }),
    ).toBeVisible();
    await page.keyboard.press("Enter");

    await expect(page).toHaveURL(new RegExp(`/task/${taskId}`));
  });

  test("footer surfaces ↑↓ navigate, ↵ run, and Esc close hints", async ({
    page,
  }) => {
    await page.getByRole("button", { name: /search tasks/i }).click();
    const dialog = page.getByRole("dialog", { name: /command palette/i });
    await expect(dialog).toContainText("navigate");
    await expect(dialog).toContainText("run");
    await expect(dialog).toContainText("close");
  });
});
