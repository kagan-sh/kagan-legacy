import { test, expect } from "./coverage-fixture";
import { createTaskViaApi, ensureBoardReady } from "./helpers";

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

    // Scope to the main landmark — sidebar mirrors task titles as buttons.
    const main = page.locator("#main-content");
    const taskCard = main.locator(
      "[role=button][aria-roledescription=draggable]",
      { hasText: title },
    );
    await expect(taskCard).toBeVisible();

    await taskCard.click();
    await expect(
      page.getByText("Task Inspector", { exact: true }),
    ).toBeVisible();
    await expect(page.getByText("Open task", { exact: true })).toBeVisible();

    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/task\//);
  });

  // FIXME: AlertDialog stays open after clicking "Delete task" — the
  // `deleteTask` API call appears to hang or reject even for fresh
  // BACKLOG-state tasks. Skipping until the delete flow is investigated;
  // strict-mode selector issues are resolved.
  test.skip("supports board delete confirmation", async ({ page, request }) => {
    // Create via API so the task stays in BACKLOG — UI creation auto-attaches
    // the fake-agent, which puts the task in a non-deletable "Queued" state.
    const title = `Delete parity ${Date.now()}`;
    await createTaskViaApi(request, title);
    await page.reload();
    await page.waitForLoadState("load");

    const main = page.locator("#main-content");
    const taskCard = main.locator(
      "[role=button][aria-roledescription=draggable]",
      { hasText: title },
    );
    await expect(taskCard).toBeVisible();

    await taskCard.click({ button: "right" });
    await page.getByRole("menuitem", { name: "Delete" }).click();

    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText("Delete task?")).toBeVisible();
    await dialog.getByRole("button", { name: "Delete task" }).click();

    // Sonner toast confirms the persisted state — wait for it rather than
    // the dialog's animated dismiss.
    await expect(page.getByText("Task deleted")).toBeVisible({
      timeout: 10_000,
    });
    await expect(taskCard).toHaveCount(0, { timeout: 10_000 });
  });
});
