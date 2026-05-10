import { test, expect } from "./coverage-fixture";
import { ensureBoardReady } from "./helpers";

test.describe("Navigation", () => {
  test.beforeEach(async ({ page, request }) => {
    await ensureBoardReady(page, request);
  });

  test("board to settings and back", async ({ page }) => {
    await page.goto("/board");
    await page.getByRole("link", { name: /^settings$/i }).click();
    await expect(page.getByText(/connection/i)).toBeVisible();
    await page.getByRole("link", { name: /kanban/i }).click();
    await expect(
      page.getByRole("heading", { name: "Backlog", exact: true }),
    ).toBeVisible();
  });
});
