import { test, expect } from "./coverage-fixture";
import { ensureBoardReady } from "./helpers";

test.describe("Settings forms", () => {
  test.beforeEach(async ({ page, request }) => {
    await ensureBoardReady(page, request);
    // Sidebar footer has a "Settings" link; title bar also has aria-label="Settings".
    // Use the sidebar one (first in DOM order) to navigate to /settings.
    await page.getByRole("link", { name: "Settings" }).first().click();
    await expect(page.getByText("Configure how Kagan works")).toBeVisible();
  });

  test("opens workflow section and shows controls", async ({ page }) => {
    await page.locator("#settings-card-workflow").click();
    await expect(page.getByRole("heading", { name: "Workflow" })).toBeVisible();

    // Review section
    await expect(page.getByText("Auto review")).toBeVisible();
    await expect(page.getByText("Require review approval")).toBeVisible();
    await expect(page.getByText("Auto-confirm single tasks")).toBeVisible();

    // Find the select inside the field that contains "Review strictness"
    const select = page
      .locator('[data-slot="field"]')
      .filter({ hasText: "Review strictness" })
      .locator("select");
    await expect(select).toBeVisible();
    await expect(select).toHaveValue("balanced");

    // Planning section
    await expect(page.getByText("Planning depth")).toBeVisible();

    // Merging section
    await expect(page.getByText("Serialize merges")).toBeVisible();
    await expect(page.getByText("Default base branch")).toBeVisible();
  });

  test("opens agents section and shows controls", async ({ page }) => {
    await page.locator("#settings-card-agents").click();
    await expect(page.getByRole("heading", { name: "Agents" })).toBeVisible();

    await expect(page.getByText("Default agent backend")).toBeVisible();
    await expect(page.getByText("Model hints")).toBeVisible();
    await expect(page.getByText("Default Claude model")).toBeVisible();
    await expect(page.getByText("Default OpenAI model")).toBeVisible();
    await expect(page.getByText("Additional instructions")).toBeVisible();

    const toggle = page.getByRole("switch", {
      name: /Use recommended backend/i,
    });
    await expect(toggle).toBeVisible();

    // Toggle on and back off
    await toggle.click();
    await expect(toggle).toHaveAttribute("data-state", "checked");
    await toggle.click();
    await expect(toggle).toHaveAttribute("data-state", "unchecked");
  });

  test("opens advanced section and shows controls", async ({ page }) => {
    await page.locator("#settings-card-advanced").click();
    await expect(page.getByRole("heading", { name: "Advanced" })).toBeVisible();

    await expect(page.getByRole("group", { name: "Appearance" })).toBeVisible();
    await expect(
      page.getByRole("group", { name: "Git identity" }),
    ).toBeVisible();
    await expect(
      page.getByRole("group", { name: "Workspace bootstrap" }),
    ).toBeVisible();
    await expect(page.getByRole("group", { name: "Attach" })).toBeVisible();

    const themeSelect = page
      .locator('[data-slot="field"]')
      .filter({ hasText: "Theme" })
      .locator("select");
    await expect(themeSelect).toBeVisible();
    await expect(themeSelect).toHaveValue("system");
  });

  test("additional instructions shows apply/discard when dirty", async ({
    page,
  }) => {
    await page.locator("#settings-card-agents").click();
    await expect(page.getByRole("heading", { name: "Agents" })).toBeVisible();

    const textarea = page
      .locator('[data-slot="field"]')
      .filter({ hasText: "Additional instructions" })
      .locator("textarea");
    await expect(textarea).toBeVisible();

    await textarea.fill("Use conventional commits");

    // Apply and Discard buttons should appear
    await expect(page.getByRole("button", { name: /Apply/i })).toBeVisible();
    await expect(page.getByRole("button", { name: /Discard/i })).toBeVisible();

    // Click discard to revert
    await page.getByRole("button", { name: /Discard/i }).click();
    await expect(textarea).toHaveValue("");
  });

  test("navigates back from section to category list", async ({ page }) => {
    await page.locator("#settings-card-workflow").click();
    await expect(page.getByRole("heading", { name: "Workflow" })).toBeVisible();

    await page.getByRole("button", { name: /All settings/i }).click();
    await expect(page.locator("#settings-card-workflow")).toBeVisible();
    await expect(page.locator("#settings-card-agents")).toBeVisible();
    await expect(page.locator("#settings-card-advanced")).toBeVisible();
  });
});
