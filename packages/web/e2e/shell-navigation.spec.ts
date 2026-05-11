import { expect, test } from "./coverage-fixture";
import { ensureBoardReady } from "./helpers";

test.describe("Shell navigation", () => {
  test.describe.configure({ timeout: 120_000 });

  test.beforeEach(async ({ page, request }) => {
    await ensureBoardReady(page, request);
  });

  test("workspace, chat, settings, and legacy redirects", async ({ page }) => {
    await test.step("title bar exposes workspace + kanban", async () => {
      await page.goto("/board");
      await expect(page.getByRole("link", { name: /workspace/i })).toBeVisible();
      await expect(page.getByRole("link", { name: /kanban/i })).toBeVisible();
    });

    await test.step("workspace tab opens chat with empty state", async () => {
      await page.goto("/board");
      await page.getByRole("link", { name: /workspace/i }).click();
      await expect(page).toHaveURL(/\/chat/);
      await page.waitForLoadState("load");
      await expect(page.getByTestId("chat-page-empty")).toBeVisible();
      await expect(page.getByText("Select a session from the sidebar")).toBeVisible();
    });

    await test.step("new session opens modal", async () => {
      await expect(page.getByRole("button", { name: "New session" })).toBeVisible();
      await page.getByRole("button", { name: "New session" }).click();
      await expect(page.getByRole("dialog", { name: "New session" })).toBeVisible({
        timeout: 5_000,
      });
      await page.getByRole("dialog", { name: "New session" }).getByRole("button", { name: "Cancel" }).click();
      await expect(page.getByRole("dialog", { name: "New session" })).toBeHidden();
    });

    await test.step("kanban tab returns to board", async () => {
      await page.getByRole("link", { name: /kanban/i }).click();
      await expect(page).toHaveURL(/\/board/);
      await expect(
        page.getByRole("heading", { name: "Backlog", exact: true }),
      ).toBeVisible();
    });

    await test.step("sidebar new task on board and chat", async () => {
      await expect(
        page.getByRole("button", { name: /new task/i }).first(),
      ).toBeVisible();
      await page.getByRole("link", { name: /workspace/i }).click();
      await expect(page).toHaveURL(/\/chat/);
      await expect(
        page.getByRole("button", { name: "New task" }).first(),
      ).toBeVisible();
    });

    await test.step("settings round-trip from sidebar", async () => {
      await page.goto("/board");
      await page.getByRole("link", { name: /^settings$/i }).first().click();
      await expect(page.getByText(/connection/i)).toBeVisible();
      await page.getByRole("link", { name: /kanban/i }).click();
      await expect(
        page.getByRole("heading", { name: "Backlog", exact: true }),
      ).toBeVisible();
    });

    await test.step("/analytics redirects to chat", async () => {
      await page.goto("/analytics");
      await expect(page).toHaveURL(/\/chat$/);
    });

    await test.step("Cmd/Ctrl+\\ toggles sidebar", async () => {
      await page.goto("/board");
      await expect(
        page.getByRole("heading", { name: "Backlog", exact: true }),
      ).toBeVisible();

      const sidebar = page.locator('aside[aria-label="Workspace sidebar"]');
      const initial = (await sidebar.getAttribute("data-collapsed")) === "true";

      const isMac = await page.evaluate(() =>
        navigator.platform.toLowerCase().includes("mac"),
      );
      await page.keyboard.press(isMac ? "Meta+\\" : "Control+\\");
      await expect(sidebar).toHaveAttribute(
        "data-collapsed",
        initial ? "false" : "true",
      );
    });
  });
});
