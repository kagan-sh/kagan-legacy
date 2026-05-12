import { expect, test } from "./coverage-fixture";
import { ensureProjectReady, waitForServerHealthy } from "./helpers";

test.describe("Welcome", () => {
  test.beforeEach(async ({ request }) => {
    await waitForServerHealthy(request);
    await ensureProjectReady(request);
  });

  test("welcome surfaces and server health", async ({ page, request }) => {
    await test.step("health endpoint returns ok", async () => {
      const resp = await request.get("/health");
      await expect(resp.ok()).toBeTruthy();
    });

    await test.step("welcome actions and dialogs", async () => {
      await page.goto("/welcome", { waitUntil: "domcontentloaded" });
      await page.waitForLoadState("load");

      await expect(
        page.getByRole("button", { name: /^new project$/i }),
      ).toBeVisible({ timeout: 60_000 });
      await expect(
        page.getByRole("button", { name: /^open folder$/i }),
      ).toBeVisible({ timeout: 60_000 });

      await page.getByRole("button", { name: /^new project$/i }).click();
      const newProjectDialog = page.getByRole("dialog", { name: /new project/i });
      await expect(newProjectDialog).toBeVisible();
      await expect(newProjectDialog.getByPlaceholder("my-project")).toBeVisible();
      await expect(newProjectDialog.getByPlaceholder("/path/to/repository")).toBeVisible();
      await page.keyboard.press("Escape");
      await expect(newProjectDialog).toBeHidden();

      await page.getByRole("button", { name: /^open folder$/i }).click();
      await expect(page.getByRole("dialog")).toBeVisible();
      await page.keyboard.press("Escape");
    });
  });
});
