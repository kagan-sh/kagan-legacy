// Consolidated: board surface, kanban inspect, list view, keyboard shortcuts,
// Spotlight (command palette), and GitHub import entry via the palette.
import { expect, test } from "./coverage-fixture";
import { createTaskViaApi, ensureBoardReady } from "./helpers";

test.describe("Board and Spotlight", () => {
  test.describe.configure({ timeout: 120_000 });

  test.beforeEach(async ({ page, request }) => {
    await ensureBoardReady(page, request);
  });

  test("columns through command palette and import", async ({ page, request }) => {
    await test.step("four columns and create affordance", async () => {
      await page.goto("/board");
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
      await expect(page.getByRole("button", { name: "Create new task" })).toBeVisible();
    });

    await test.step("create task, inspector, Enter opens task route", async () => {
      const title = `Inspector parity ${Date.now()}`;
      await page.getByRole("button", { name: "Create new task" }).click();
      await page.getByPlaceholder("What needs to be done?").fill(title);
      await page.getByRole("button", { name: "Create" }).click();

      const main = page.locator("#main-content");
      const taskCard = main.locator("[role=button][aria-roledescription=draggable]", {
        hasText: title,
      });
      await expect(taskCard).toBeVisible();

      await taskCard.click();
      await expect(page.getByText("Task Inspector", { exact: true })).toBeVisible();
      await expect(page.getByText("Open task", { exact: true })).toBeVisible();

      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(/\/task\//);
      await page.goto("/board");
      await page.waitForLoadState("load");
    });

    await test.step("Spotlight search, no-results, and list vs board view", async () => {
      const uniqueTitle = `UniqueSearchTerm ${Date.now()}`;
      await createTaskViaApi(request, uniqueTitle);

      await expect(
        page.getByRole("heading", { name: "Backlog", exact: true }),
      ).toBeVisible();

      await page.getByRole("button", { name: /search tasks/i }).click();
      const palette = page.getByRole("dialog", { name: /command palette/i });
      await expect(palette).toBeVisible({ timeout: 5_000 });

      const input = palette.getByPlaceholder(/search tasks, run commands/i);
      await input.fill("NonExistentQuery12345zzzNotReal");
      await expect(palette.getByText(/no results/i)).toBeVisible({ timeout: 3_000 });

      await input.fill("");
      await input.fill(uniqueTitle.slice(0, 12));
      await expect(palette.getByText(uniqueTitle)).toBeVisible({ timeout: 5_000 });

      await input.press("Escape");
      await expect(palette).toBeHidden();

      await page.getByRole("button", { name: "List view" }).click();
      await expect(page.getByRole("button", { name: /^ID/i })).toBeVisible();

      const sortTitle = `ColSort ${Date.now()}`;
      await createTaskViaApi(request, sortTitle);
      await page.reload();
      await page.waitForLoadState("load");
      await page.getByRole("button", { name: "List view" }).click();
      await expect(page.getByRole("button", { name: /^Status/i })).toBeVisible();
      const main = page.locator("#main-content");
      await expect(main.locator("[data-task-id]", { hasText: sortTitle })).toBeVisible();

      await page.getByRole("button", { name: "Board view" }).click();
      await expect(page.getByRole("heading", { name: "Backlog" })).toBeVisible();
    });

    await test.step("list keyboard navigation and Enter", async () => {
      const t1 = `KB1 ${Date.now()}`;
      const t2 = `KB2 ${Date.now()}`;
      await createTaskViaApi(request, t1);
      await createTaskViaApi(request, t2);

      await page.goto("/board");
      await page.waitForLoadState("load");
      await page.getByRole("button", { name: "List view" }).click();

      const main = page.locator("#main-content");
      const row1 = main.locator("[data-task-id]", { hasText: t1 });
      const row2 = main.locator("[data-task-id]", { hasText: t2 });

      await row1.click();
      await expect(row1).toHaveAttribute("aria-pressed", "true");

      await page.keyboard.press("ArrowDown");
      await expect(row2).toHaveAttribute("aria-pressed", "true");

      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(/\/task\//);
      await page.goto("/board");
      await page.waitForLoadState("load");
    });

    await test.step("'e' opens edit dialog from kanban card", async () => {
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
      await page.keyboard.press("Escape");
      await expect(page.getByRole("dialog", { name: /edit task/i })).toBeHidden();
    });

    await test.step("Cmd/Ctrl+K opens Spotlight", async () => {
      const isMac = await page.evaluate(() =>
        navigator.platform.toLowerCase().includes("mac"),
      );
      await page.keyboard.press(isMac ? "Meta+k" : "Control+k");
      await expect(
        page.getByRole("dialog", { name: /command palette/i }),
      ).toBeVisible({ timeout: 5_000 });
      await page.keyboard.press("Escape");
    });

    await test.step("Spotlight Enter navigates to task; footer hints; Escape", async () => {
      const taskId = await createTaskViaApi(request, "Spotlight target xyz unique");
      await page.goto("/board");

      await page.getByRole("button", { name: /search tasks/i }).click();
      const palette = page.getByRole("dialog", { name: /command palette/i });
      await expect(palette).toBeVisible({ timeout: 5_000 });

      const input = palette.getByPlaceholder(/search tasks, run commands/i);
      await input.fill("Spotlight target xyz");
      await expect(
        palette.getByRole("option").filter({ hasText: /spotlight target xyz/i }),
      ).toBeVisible();
      await page.keyboard.press("Enter");
      await expect(page).toHaveURL(new RegExp(`/task/${taskId}`));

      await page.goto("/board");
      await page.getByRole("button", { name: /search tasks/i }).click();
      const palette2 = page.getByRole("dialog", { name: /command palette/i });
      await expect(palette2).toBeVisible();
      await expect(palette2).toContainText("navigate");
      await expect(palette2).toContainText("run");
      await expect(palette2).toContainText("close");
      await palette2.getByPlaceholder(/search tasks, run commands/i).press("Escape");
      await expect(palette2).toBeHidden();
    });

    await test.step("Import from GitHub via Spotlight", async () => {
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

      const dialog = page.getByRole("dialog", { name: /import from github/i });
      await expect(dialog).toBeVisible();
      await expect(
        dialog.getByRole("heading", { name: /import from github/i }),
      ).toBeVisible();
      await expect(dialog.locator("#integration-repo")).toBeVisible({
        timeout: 10_000,
      });
      await expect(dialog.getByRole("button", { name: /preview/i })).toBeVisible();
      await dialog.getByRole("button", { name: /cancel/i }).click();
      await expect(dialog).toBeHidden();
    });
  });

  // FIXME: AlertDialog stays open after clicking "Delete task" — investigate delete API.
  test.skip("board delete confirmation", async ({ page, request }) => {
    const title = `Delete parity ${Date.now()}`;
    await createTaskViaApi(request, title);
    await page.goto("/board");
    await page.waitForLoadState("load");

    const main = page.locator("#main-content");
    const taskCard = main.locator("[role=button][aria-roledescription=draggable]", {
      hasText: title,
    });
    await expect(taskCard).toBeVisible();

    await taskCard.click({ button: "right" });
    await page.getByRole("menuitem", { name: "Delete" }).click();

    const dialog = page.getByRole("alertdialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText("Delete task?")).toBeVisible();
    await dialog.getByRole("button", { name: "Delete task" }).click();

    await expect(page.getByText("Task deleted")).toBeVisible({
      timeout: 10_000,
    });
    await expect(taskCard).toHaveCount(0, { timeout: 10_000 });
  });
});
