import { test, expect } from "./coverage-fixture";
import { ensureBoardReady } from "./helpers";

test.describe("Board", () => {
  test.beforeEach(async ({ page, request }) => {
    await ensureBoardReady(page, request);
  });

  test("shows 4 columns", async ({ page }) => {
    await expect(
      page.getByRole("heading", { name: "Backlog", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "In Progress", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Review", exact: true }),
    ).toBeVisible();
    await expect(
      page.getByRole("heading", { name: "Done", exact: true }),
    ).toBeVisible();
  });

  test("shows new-task button", async ({ page }) => {
    // Board toolbar uses aria-label="Create new task" in the new shell.
    await expect(
      page.getByRole("button", { name: "Create new task" }),
    ).toBeVisible();
  });

  test("supports desktop inspect and task-open flow", async ({ page }) => {
    const title = `Inspector parity ${Date.now()}`;

    await page.getByRole("button", { name: "Create new task" }).click();
    await page.getByPlaceholder("What needs to be done?").fill(title);
    await page.getByRole("button", { name: "Create" }).click();

    const taskCard = page.getByRole("button", { name: title });
    await expect(taskCard).toBeVisible();

    await taskCard.click();
    await expect(
      page.getByText("Task Inspector", { exact: true }),
    ).toBeVisible();
    await expect(page.getByText("Open task", { exact: true })).toBeVisible();

    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/task\//);
  });

  test("supports board delete confirmation", async ({ page }) => {
    const title = `Delete parity ${Date.now()}`;

    await page.getByRole("button", { name: "Create new task" }).click();
    await page.getByPlaceholder("What needs to be done?").fill(title);
    await page.getByRole("button", { name: "Create" }).click();

    const taskCard = page.getByRole("button", { name: title });
    await expect(taskCard).toBeVisible();

    await taskCard.click({ button: "right" });
    await page.getByRole("menuitem", { name: "Delete" }).click();

    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText("Delete task?")).toBeVisible();
    await dialog.getByRole("button", { name: "Delete task" }).click();

    await expect(page.getByRole("button", { name: title })).toHaveCount(0);
  });
});
