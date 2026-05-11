import { expect, test } from "./coverage-fixture";
import { ensureProjectReady, waitForServerHealthy } from "./helpers";

test.describe("Welcome flow", () => {
  test.beforeEach(async ({ request }) => {
    await waitForServerHealthy(request);
    // The shared fixture seeds a project — /welcome must still render
    // its action chrome (New project / Open folder) when one exists.
    await ensureProjectReady(request);
  });

  test("welcome page renders New project + Open folder actions", async ({
    page,
  }) => {
    await page.goto("/welcome");

    await expect(
      page.getByRole("button", { name: /^new project$/i }),
    ).toBeVisible();
    await expect(
      page.getByRole("button", { name: /^open folder$/i }),
    ).toBeVisible();
  });

  test("New project opens the create-project dialog with a name field", async ({
    page,
  }) => {
    await page.goto("/welcome");
    // Wait for React hydration — under coverage-instrumented builds the
    // button is in the DOM before its onClick handler is wired up.
    const trigger = page.getByRole("button", { name: /^new project$/i });
    await expect(trigger).toBeEnabled();
    await trigger.click();

    const dialog = page.getByRole("dialog", { name: /new project/i });
    await expect(dialog).toBeVisible({ timeout: 10_000 });
    await expect(dialog.getByPlaceholder("my-project")).toBeVisible();
    await expect(dialog.getByPlaceholder("/path/to/repository")).toBeVisible();
  });

  test("Open folder picker is reachable from welcome", async ({ page }) => {
    await page.goto("/welcome");
    const trigger = page.getByRole("button", { name: /^open folder$/i });
    await expect(trigger).toBeEnabled();
    await trigger.click();
    // Path picker is implemented as a Radix dialog that lists directory rows.
    await expect(page.getByRole("dialog")).toBeVisible({ timeout: 10_000 });
  });
});
