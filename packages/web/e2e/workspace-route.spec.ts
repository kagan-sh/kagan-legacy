// Workspace tab (/chat) now uses the chat-page surface — a ws-head + composer.
// The old workspace sidebar (Chat sessions, New chat, Filter sessions...) is gone;
// session management lives in the shell sidebar (New session button, sessions list).
import { test, expect } from "./coverage-fixture";
import { ensureBoardReady, ensureProjectReady } from "./helpers";

test.describe("Workspace route", () => {
  test.beforeEach(async ({ page, request }) => {
    await ensureBoardReady(page, request);
  });

  test("shows empty-state prompt when no session is selected", async ({ page }) => {
    await page.goto("/chat");
    await page.waitForLoadState("load");

    // chat-page renders an empty state when no session id is in the URL.
    await expect(page.getByTestId("chat-page-empty")).toBeVisible();
    await expect(page.getByText("Select a session from the sidebar")).toBeVisible();
  });

  test("sidebar New session button opens the session creation modal", async ({ page }) => {
    await page.goto("/chat");
    await page.waitForLoadState("load");

    // Shell sidebar always has "New session" regardless of active tab.
    await expect(
      page.getByRole("button", { name: "New session" }),
    ).toBeVisible();
    await page.getByRole("button", { name: "New session" }).click();

    // New-session modal should appear.
    await expect(page.getByRole("dialog")).toBeVisible({ timeout: 5_000 });
  });

  test("navigating to /chat from the title bar Workspace tab works", async ({ page }) => {
    await page.goto("/board");
    await page.getByRole("link", { name: /workspace/i }).click();
    await expect(page).toHaveURL(/\/chat/);
  });

  test("sidebar exposes New task action while on workspace tab", async ({ page }) => {
    await page.goto("/chat");
    await page.waitForLoadState("load");

    await expect(
      page.getByRole("button", { name: "New task" }).first(),
    ).toBeVisible();
  });
});
