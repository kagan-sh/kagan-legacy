import { test, expect } from "./coverage-fixture";
import { createTaskViaApi, ensureBoardReady } from "./helpers";

test.describe("Task edit and delete", () => {
  test.beforeEach(async ({ page, request }) => {
    await ensureBoardReady(page, request);
  });

  test("edits task title from detail page via keyboard shortcut", async ({
    page,
    request,
  }) => {
    const title = `Edit me ${Date.now()}`;
    const taskId = await createTaskViaApi(request, title);

    await page.goto(`/task/${taskId}`);
    await page.waitForLoadState("load");
    await expect(page).toHaveURL(/\/task\//);

    // Click on a non-editable area to ensure focus, then press 'e'
    await page.locator("h1").first().click();
    await page.keyboard.press("e");

    const dialog = page.getByRole("dialog", { name: "Edit Task" });
    await expect(dialog).toBeVisible();

    const titleInput = dialog.getByLabel("Title");
    await expect(titleInput).toHaveValue(title);

    const newTitle = `Edited ${Date.now()}`;
    await titleInput.fill(newTitle);
    await dialog.getByRole("button", { name: "Save" }).click();

    // Dialog should close
    await expect(dialog).toBeHidden();

    // Reload to verify persistence (task detail may not re-fetch immediately).
    // Sidebar mirrors task titles, so scope to the page heading.
    await page.reload();
    await page.waitForLoadState("load");
    await expect(page.getByRole("heading", { name: newTitle })).toBeVisible();
  });

  test("edits task description from detail page", async ({ page, request }) => {
    const title = `Desc edit ${Date.now()}`;
    const taskId = await createTaskViaApi(request, title);

    await page.goto(`/task/${taskId}`);
    await page.waitForLoadState("load");

    await page.locator("h1").first().click();
    await page.keyboard.press("e");

    const dialog = page.getByRole("dialog", { name: "Edit Task" });
    await expect(dialog).toBeVisible();

    const descInput = dialog.getByLabel("Description");
    const newDesc = "This is the updated description.";
    await descInput.fill(newDesc);
    await dialog.getByRole("button", { name: "Save" }).click();

    await expect(dialog).toBeHidden();

    // Reload and verify description persisted
    await page.reload();
    await page.waitForLoadState("load");
    await expect(page.getByText(newDesc)).toBeVisible();
  });

  test("cancels edit dialog without saving", async ({ page, request }) => {
    const title = `Cancel edit ${Date.now()}`;
    const taskId = await createTaskViaApi(request, title);

    await page.goto(`/task/${taskId}`);
    await page.waitForLoadState("load");

    await page.locator("h1").first().click();
    await page.keyboard.press("e");

    const dialog = page.getByRole("dialog", { name: "Edit Task" });
    await expect(dialog).toBeVisible();

    const titleInput = dialog.getByLabel("Title");
    await titleInput.fill("Should not save");
    await dialog.getByRole("button", { name: "Cancel" }).click();

    await expect(dialog).toBeHidden();

    // Reload and verify original title persisted — page heading carries the
    // title; sidebar mirrors it as a span, so scope by heading role.
    await page.reload();
    await page.waitForLoadState("load");
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
    await expect(page.getByText("Should not save")).toHaveCount(0);
  });
});
