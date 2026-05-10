import { test, expect } from "./coverage-fixture";
import { ensureBoardReady } from "./helpers";

test.describe("Navigation", () => {
  test.beforeEach(async ({ page, request }) => {
    await ensureBoardReady(page, request);
  });

  test("board to settings and back", async ({ page }) => {
    await page.goto("/board");
    // Sidebar footer link (text "Settings") and title-bar icon link (aria-label="Settings")
    // both match — use the sidebar one (first) which is the primary nav surface.
    await page.getByRole("link", { name: /^settings$/i }).first().click();
    await expect(page.getByText(/connection/i)).toBeVisible();
    await page.getByRole("link", { name: /kanban/i }).click();
    await expect(
      page.getByRole("heading", { name: "Backlog", exact: true }),
    ).toBeVisible();
  });

  test("retired /analytics route redirects through workspace to chat", async ({
    page,
  }) => {
    await page.goto("/analytics");
    // /analytics → /workspace → /chat (two-hop redirect chain in routes.tsx).
    await expect(page).toHaveURL(/\/chat$/);
  });
});
