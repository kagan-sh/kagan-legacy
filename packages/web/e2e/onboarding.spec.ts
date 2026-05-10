import { test, expect } from "./coverage-fixture";
import { waitForServerHealthy } from "./helpers";

test.describe("Onboarding", () => {
  test("welcome page loads with project setup", async ({ page, request }) => {
    await waitForServerHealthy(request);

    await page.goto("/welcome");
    await page.waitForLoadState("load");

    await expect(
      page.getByRole("button", { name: "New Project" }),
    ).toBeVisible();
  });

  test("health endpoint returns ok", async ({ request }) => {
    const resp = await request.get("/health");
    await expect(resp.ok()).toBeTruthy();
  });
});
