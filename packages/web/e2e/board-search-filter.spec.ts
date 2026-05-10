// Board search and filter tests.
// The inline "Search tasks" textbox is gone from the new shell — search is
// handled via the Spotlight (Cmd+K). Board inline filtering uses the Filter
// popover. View switching now uses "Board view" / "List view" buttons
// (aria-label) instead of radio inputs.
import { test, expect } from "./coverage-fixture";
import { ensureBoardReady, createTaskViaApi } from "./helpers";

test.describe("Board search and filter", () => {
  test.beforeEach(async ({ page, request }) => {
    await ensureBoardReady(page, request);
  });

  test("Spotlight filters tasks by title", async ({ page, request }) => {
    const title = `UniqueSearchTerm ${Date.now()}`;
    await createTaskViaApi(request, title);

    await page.goto("/board");
    await page.waitForLoadState("load");

    // Open Spotlight via Cmd/Ctrl+K and search for the task.
    const isMac = await page.evaluate(() =>
      navigator.platform.toLowerCase().includes("mac"),
    );
    await page.keyboard.press(isMac ? "Meta+k" : "Control+k");
    const dialog = page.getByRole("dialog", { name: /command palette/i });
    await expect(dialog).toBeVisible({ timeout: 5_000 });

    const input = dialog.getByPlaceholder(/search tasks, run commands/i);
    await input.fill(title.slice(0, 12));

    // The matching task should appear in the spotlight list.
    await expect(dialog.getByText(title)).toBeVisible({ timeout: 5_000 });
  });

  test("Spotlight shows no-results state for unmatched query", async ({ page }) => {
    await page.goto("/board");
    await page.waitForLoadState("load");

    const isMac = await page.evaluate(() =>
      navigator.platform.toLowerCase().includes("mac"),
    );
    await page.keyboard.press(isMac ? "Meta+k" : "Control+k");
    const dialog = page.getByRole("dialog", { name: /command palette/i });
    await expect(dialog).toBeVisible({ timeout: 5_000 });

    const input = dialog.getByPlaceholder(/search tasks, run commands/i);
    await input.fill("NonExistentQuery12345zzzNotReal");

    await expect(dialog.getByText(/no results/i)).toBeVisible({ timeout: 3_000 });
  });

  test("board list view toggle switches from kanban to list", async ({ page }) => {
    // New toolbar: "Board view" / "List view" buttons (not radio inputs).
    await page.getByRole("button", { name: "List view" }).click();
    // List view renders the backlog table — ID column header is a sort button.
    await expect(page.getByRole("button", { name: /^ID/i })).toBeVisible();

    await page.getByRole("button", { name: "Board view" }).click();
    await expect(page.getByRole("heading", { name: "Backlog" })).toBeVisible();
  });

  test("list view exposes sortable column headers", async ({ page, request }) => {
    const title = `ColSort ${Date.now()}`;
    await createTaskViaApi(request, title);

    await page.goto("/board");
    await page.waitForLoadState("load");

    await page.getByRole("button", { name: "List view" }).click();

    // BacklogListView renders ID, Title, Status, Agent, Duration sort buttons.
    await expect(page.getByRole("button", { name: /^ID/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /^Status/i })).toBeVisible();

    // The created task should appear as a row button.
    await expect(page.getByRole("button", { name: title })).toBeVisible();
  });
});
