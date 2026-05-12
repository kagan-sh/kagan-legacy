import { expect, test } from "./coverage-fixture";
import { ensureProjectReady, waitForServerHealthy } from "./helpers";

test.describe("Welcome", () => {
  test.describe.configure({ timeout: 120_000 });

  test.beforeEach(async ({ request }) => {
    await waitForServerHealthy(request);
    await ensureProjectReady(request);
  });

  test("welcome surfaces and server health", async ({ page, request }) => {
    await test.step(
      "health endpoint returns ok",
      async () => {
        const resp = await request.get("/health");
        await expect(resp.ok()).toBeTruthy();
      },
      { timeout: 120_000 },
    );

    await test.step(
      "welcome actions and dialogs",
      async () => {
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
        await expect(newProjectDialog).toBeVisible({ timeout: 30_000 });
        await expect(newProjectDialog.getByPlaceholder("my-project")).toBeVisible({
          timeout: 15_000,
        });
        await expect(newProjectDialog.getByPlaceholder("/path/to/repository")).toBeVisible({
          timeout: 15_000,
        });
        await page.keyboard.press("Escape");
        await expect(newProjectDialog).toBeHidden();

        await page.getByRole("button", { name: /^open folder$/i }).click();
        await expect(page.getByRole("dialog")).toBeVisible();
        await page.keyboard.press("Escape");
      },
      { timeout: 120_000 },
    );
  });
});
