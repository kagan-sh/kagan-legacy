import { test, expect } from "./coverage-fixture";
import {
  ensureBoardReady,
  createTaskAndRun,
  waitForTaskSessions,
} from "./helpers";

test.describe("Task Changes tab", () => {
  test("shows changes tab for a running task", async ({ page, request }) => {
    await ensureBoardReady(page, request);
    const title = `ChangesTab ${Date.now()}`;
    const taskId = await createTaskAndRun(request, title);
    await waitForTaskSessions(request, taskId);

    await page.goto(`/task/${taskId}`);
    await page.waitForLoadState("load");

    await page.getByRole("tab", { name: "Changes" }).click();
    await expect(page.getByRole("tab", { name: "Changes" })).toHaveAttribute(
      "data-state",
      "active",
    );

    // A running task with workspace but no commits shows the no-changes-yet state
    await expect(page.getByText("No code changes yet")).toBeVisible();
  });
});
