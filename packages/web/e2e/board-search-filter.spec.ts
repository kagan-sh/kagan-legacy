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
    // The board content must render at least the Backlog heading before the
    // global Cmd+K handler is attached. Without this wait, Spotlight may not
    // open on the first keypress under coverage-instrumented builds.
    await expect(
      page.getByRole("heading", { name: "Backlog", exact: true }),
    ).toBeVisible();

    // Open Spotlight via the header search trigger (more reliable than the
    // keyboard chord on a hydrating page).
    await page.getByRole("button", { name: /search tasks/i }).click();
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
    await expect(
      page.getByRole("heading", { name: "Backlog", exact: true }),
    ).toBeVisible();

    // Header search trigger is more reliable than the keyboard chord on
    // coverage-instrumented builds.
    await page.getByRole("button", { name: /search tasks/i }).click();
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

    // The created task should appear as a row in the main list (sidebar
    // mirrors task titles, so scope the selector to the main landmark).
    const main = page.locator("#main-content");
    await expect(
      main.locator("[data-task-id]", { hasText: title }),
    ).toBeVisible();
  });
});
