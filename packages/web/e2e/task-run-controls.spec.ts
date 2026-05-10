import { test, expect } from "./coverage-fixture";
import { ensureBoardReady, createTaskViaApi, waitForTaskStatus } from "./helpers";

test.describe("Task run controls", () => {
  test.beforeEach(async ({ page, request }) => {
    await ensureBoardReady(page, request);
  });

  test("start button transitions task to IN_PROGRESS", async ({ page, request }) => {
    const title = `RunControl ${Date.now()}`;
    const taskId = await createTaskViaApi(request, title);

    await page.goto(`/task/${taskId}`);
    await page.waitForLoadState("load");

    await page.getByRole("button", { name: "Start" }).click();

    // The task should transition to IN_PROGRESS
    await waitForTaskStatus(request, taskId, "IN_PROGRESS", { timeoutMs: 15_000 });

    // After run starts, a Stop button should appear
    await expect(page.getByRole("button", { name: "Stop" })).toBeVisible();
  });
});
