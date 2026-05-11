import { expect, test } from "./coverage-fixture";
import { ensureBoardReady } from "./helpers";

test.describe("Settings", () => {
  test.beforeEach(async ({ page, request }) => {
    await ensureBoardReady(page, request);
    await page.getByRole("link", { name: "Settings" }).first().click();
    await expect(page.getByText("Configure how Kagan works")).toBeVisible();
  });

  test("workflow, agents, advanced, and dirty discard", async ({ page }) => {
    await test.step("workflow controls", async () => {
      await page.locator("#settings-card-workflow").click();
      await expect(page.getByRole("heading", { name: "Workflow" })).toBeVisible();

      await expect(page.getByText("Auto review")).toBeVisible();
      await expect(page.getByText("Require review approval")).toBeVisible();
      await expect(page.getByText("Auto-confirm single tasks")).toBeVisible();

      const select = page
        .locator('[data-slot="field"]')
        .filter({ hasText: "Review strictness" })
        .locator("select");
      await expect(select).toBeVisible();
      await expect(select).toHaveValue("balanced");

      await expect(page.getByText("Planning depth")).toBeVisible();
      await expect(page.getByText("Serialize merges")).toBeVisible();
      await expect(page.getByText("Default base branch")).toBeVisible();

      await page.getByRole("button", { name: /All settings/i }).click();
    });

    await test.step("agents toggle and additional instructions dirty state", async () => {
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
      await toggle.click();
      await expect(toggle).toHaveAttribute("data-state", "checked");
      await toggle.click();
      await expect(toggle).toHaveAttribute("data-state", "unchecked");

      const textarea = page
        .locator('[data-slot="field"]')
        .filter({ hasText: "Additional instructions" })
        .locator("textarea");
      await expect(textarea).toBeVisible();
      await textarea.fill("Use conventional commits");

      await expect(page.getByRole("button", { name: /Apply/i })).toBeVisible();
      await expect(page.getByRole("button", { name: /Discard/i })).toBeVisible();
      await page.getByRole("button", { name: /Discard/i }).click();
      await expect(textarea).toHaveValue("");

      await page.getByRole("button", { name: /All settings/i }).click();
    });

    await test.step("advanced groups", async () => {
      await page.locator("#settings-card-advanced").click();
      await expect(page.getByRole("heading", { name: "Advanced" })).toBeVisible();

      await expect(page.getByRole("group", { name: "Appearance" })).toBeVisible();
      await expect(page.getByRole("group", { name: "Git identity" })).toBeVisible();
      await expect(page.getByRole("group", { name: "Workspace bootstrap" })).toBeVisible();
      await expect(page.getByRole("group", { name: "Attach" })).toBeVisible();

      const themeSelect = page
        .locator('[data-slot="field"]')
        .filter({ hasText: "Theme" })
        .locator("select");
      await expect(themeSelect).toBeVisible();
      await expect(themeSelect).toHaveValue("system");

      await page.getByRole("button", { name: /All settings/i }).click();
    });

    await test.step("category cards remain reachable", async () => {
      await expect(page.locator("#settings-card-workflow")).toBeVisible();
      await expect(page.locator("#settings-card-agents")).toBeVisible();
      await expect(page.locator("#settings-card-advanced")).toBeVisible();
    });
  });
});
