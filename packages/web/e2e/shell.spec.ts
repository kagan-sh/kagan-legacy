import { test, expect } from "./coverage-fixture";
import { ensureBoardReady } from "./helpers";

test.describe("Shell layout", () => {
  test.beforeEach(async ({ page, request }) => {
    await ensureBoardReady(page, request);
  });

  test("title bar exposes both workspace tabs", async ({ page }) => {
    await page.goto("/board");
    await expect(page.getByRole("link", { name: /workspace/i })).toBeVisible();
    await expect(page.getByRole("link", { name: /kanban/i })).toBeVisible();
  });

  test("clicking the Workspace tab navigates to /chat", async ({ page }) => {
    await page.goto("/board");
    await page.getByRole("link", { name: /workspace/i }).click();
    await expect(page).toHaveURL(/\/chat/);
  });

  test("clicking the Kanban tab navigates to /board", async ({ page }) => {
    await page.goto("/chat");
    await page.getByRole("link", { name: /kanban/i }).click();
    await expect(page).toHaveURL(/\/board/);
  });

  test("sidebar exposes the New task action", async ({ page }) => {
    await page.goto("/board");
    await expect(
      page.getByRole("button", { name: /new task/i }).first(),
    ).toBeVisible();
  });

  test("sidebar Settings link reaches /settings", async ({ page }) => {
    await page.goto("/board");
    // Sidebar footer "Settings" link (text) and title-bar "Settings" icon link
    // (aria-label) both match. Use the sidebar one via first().
    await page.getByRole("link", { name: /^settings$/i }).first().click();
    await expect(page).toHaveURL(/\/settings/);
  });

  test("Cmd/Ctrl+\\ toggles the sidebar", async ({ page }) => {
    await page.goto("/board");
    const isMac = await page.evaluate(() =>
      navigator.platform.toLowerCase().includes("mac"),
    );
    const sidebar = page.getByRole("complementary", {
      name: /workspace sidebar/i,
    });
    await expect(sidebar).toHaveAttribute("data-collapsed", "false");
    await page.keyboard.press(isMac ? "Meta+\\" : "Control+\\");
    await expect(sidebar).toHaveAttribute("data-collapsed", "true");
  });
});
