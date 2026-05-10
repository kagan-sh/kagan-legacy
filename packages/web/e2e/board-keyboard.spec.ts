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

    // Click first task to select it
    await page.getByRole("button", { name: t1 }).click();
    await expect(page.getByRole("button", { name: t1 })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    await page.keyboard.press("ArrowDown");
    await expect(page.getByRole("button", { name: t2 })).toHaveAttribute(
      "aria-pressed",
      "true",
    );
  });

  test("Enter opens selected task", async ({ page, request }) => {
    const title = `KBEnter ${Date.now()}`;
    await createTaskViaApi(request, title);

    await page.goto("/board");
    await page.waitForLoadState("load");
    await page.getByRole("button", { name: title }).click();

    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/task\//);
  });
});
