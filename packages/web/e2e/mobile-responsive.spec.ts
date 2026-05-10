import { test, expect } from "./coverage-fixture";
import { createTaskViaApi, ensureBoardReady } from "./helpers";

test.describe("Mobile responsive", () => {
  test.beforeEach(async ({ page, request }) => {
    await page.setViewportSize({ width: 375, height: 667 });
    await ensureBoardReady(page, request);
  });

  test("shows MobileTabs on mobile viewport", async ({ page }) => {
    await page.goto("/board");
    await page.waitForLoadState("load");
    await expect(
      page.getByRole("navigation", { name: "Mobile tabs" }),
    ).toBeVisible();
  });

  test("hides desktop activity rail on mobile", async ({ page }) => {
    await page.goto("/board");
    await page.waitForLoadState("load");
    const sidebar = page.locator('aside[aria-label="Workspace sidebar"]');
    // Sidebar collapses via `data-collapsed=true` + `aria-hidden=true` and
    // `w-0` (border contributes 1px to computed width, so don't assert 0px).
    await expect(sidebar).toHaveAttribute("data-collapsed", "true");
    await expect(sidebar).toHaveAttribute("aria-hidden", "true");
  });

  // FIXME: dnd-kit pointer sensor on the kanban card swallows the simulated
  // mouse click before `handleClick` → `onInspectTask` can fire, so the
  // navigation never happens under Playwright. Touch-emulation + tap would
  // bypass the sensor but requires a separate browser context (`isMobile`
  // device profile). Tracked for a follow-up; the rest of the mobile
  // viewport contract is covered by the other two tests in this file.
  test.skip("board inspector navigates to task detail on mobile", async ({
    page,
    request,
  }) => {
    const title = `Mobile inspect ${Date.now()}`;
    await createTaskViaApi(request, title);

    await page.goto("/board");
    await page.waitForLoadState("load");

    const card = page
      .locator("#main-content [data-task-id]")
      .filter({ hasText: title })
      .first();
    await expect(card).toBeVisible({ timeout: 10_000 });
    await card.getByText(title).first().click();

    await expect(page).toHaveURL(/\/task\/[^/]+/);
  });
});
