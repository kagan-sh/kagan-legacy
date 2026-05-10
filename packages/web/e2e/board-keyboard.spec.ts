import { test, expect } from "./coverage-fixture";
import { ensureBoardReady, createTaskViaApi } from "./helpers";

test.describe("Board keyboard shortcuts", () => {
  test.beforeEach(async ({ page, request }) => {
    await ensureBoardReady(page, request);
  });

  test("ArrowDown selects next task in backlog view", async ({ page, request }) => {
    const t1 = `KB1 ${Date.now()}`;
    const t2 = `KB2 ${Date.now()}`;
    await createTaskViaApi(request, t1);
    await createTaskViaApi(request, t2);

    await page.goto("/board");
    await page.waitForLoadState("load");
    // New toolbar: view toggle uses buttons with aria-label, not radio inputs.
    await page.getByRole("button", { name: "List view" }).click();

    // Scope to the main landmark — sidebar mirrors task titles as buttons.
    // `[data-task-id]` covers both the list-view row (`<button>`) and the
    // kanban card (`<div role=button>`) variants.
    const main = page.locator("#main-content");
    const row1 = main.locator("[data-task-id]", { hasText: t1 });
    const row2 = main.locator("[data-task-id]", { hasText: t2 });

    await row1.click();
    await expect(row1).toHaveAttribute("aria-pressed", "true");

    await page.keyboard.press("ArrowDown");
    await expect(row2).toHaveAttribute("aria-pressed", "true");
  });

  test("Enter opens selected task", async ({ page, request }) => {
    const title = `KBEnter ${Date.now()}`;
    await createTaskViaApi(request, title);

    await page.goto("/board");
    await page.waitForLoadState("load");
    const main = page.locator("#main-content");
    await main
      .locator("[role=button][aria-roledescription=draggable]", {
        hasText: title,
      })
      .click();

    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/task\//);
  });

  test("'e' opens the edit dialog for the selected task", async ({
    page,
    request,
  }) => {
    const title = `KBEdit ${Date.now()}`;
    await createTaskViaApi(request, title);

    await page.goto("/board");
    await page.waitForLoadState("load");
    const card = page
      .locator('[role="button"][aria-roledescription="draggable"]')
      .filter({ hasText: title });
    await card.click();

    await page.keyboard.press("e");
    await expect(page.getByRole("dialog", { name: /edit task/i })).toBeVisible();
  });

});
