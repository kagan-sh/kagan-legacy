import { test, expect, type APIRequestContext } from "./coverage-fixture";
import {
  ensureBoardReady,
  ensureProjectReady,
  scheduleScenario,
  reviewGate,
  waitForTaskStatus,
} from "./helpers";

async function createReviewTask(
  request: APIRequestContext,
  title: string,
  criteria: string[] = ["Code follows style guide"],
): Promise<string> {
  const { repoId } = await ensureProjectReady(request);

  const created = await request.post("/api/tasks", {
    data: { title, repo_id: repoId, acceptance_criteria: criteria },
  });
  expect(created.ok()).toBeTruthy();
  const envelope = (await created.json()) as {
    ok: boolean;
    data?: { id: string };
  };
  expect(envelope.ok).toBeTruthy();
  const taskId = envelope.data!.id;

  await scheduleScenario(request, reviewGate(taskId, "feature.md", "# Hello"));
  const runResp = await request.post(`/api/tasks/${taskId}/run`, {
    data: { agent_backend: "fake-agent" },
  });
  expect(runResp.ok()).toBeTruthy();

  await waitForTaskStatus(request, taskId, "REVIEW", { timeoutMs: 15_000 });
  return taskId;
}

test.describe("Review panel", () => {
  test.beforeEach(async ({ page, request }) => {
    await ensureBoardReady(page, request);
  });

  test("shows review panel for REVIEW task with acceptance criteria", async ({
    page,
    request,
  }) => {
    const taskId = await createReviewTask(
      request,
      `Review panel ${Date.now()}`,
      ["Code follows style guide", "Tests pass"],
    );

    await page.goto(`/task/${taskId}`);
    await page.waitForLoadState("load");

    await expect(page.getByRole("tab", { name: "Review" })).toHaveAttribute(
      "data-state",
      "active",
    );
    await expect(page.getByText("Review snapshot")).toBeVisible();
    await expect(page.getByRole("button", { name: "Approve" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Reject" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Merge" })).toBeVisible();
    await expect(page.getByRole("button", { name: "Rebase" })).toBeVisible();
  });

  test("approves a task from review panel", async ({ page, request }) => {
    const taskId = await createReviewTask(
      request,
      `Approve test ${Date.now()}`,
    );

    await page.goto(`/task/${taskId}`);
    await page.waitForLoadState("load");

    // Task title contains "Approve" so the sidebar mirror also matches —
    // exact:true picks only the review-panel action button.
    await page.getByRole("button", { name: "Approve", exact: true }).click();
    await expect(page.getByText("Task approved")).toBeVisible({
      timeout: 5_000,
    });
  });

  test("rejects a task from review panel with feedback", async ({
    page,
    request,
  }) => {
    const taskId = await createReviewTask(
      request,
      `Reject test ${Date.now()}`,
    );

    await page.goto(`/task/${taskId}`);
    await page.waitForLoadState("load");

    const feedbackText = "Needs more tests";
    await page
      .locator('textarea[placeholder="Optional feedback..."]')
      .fill(feedbackText);

    // Same disambiguation — title contains "Reject"; exact:true picks the
    // review-panel destructive button.
    await page.getByRole("button", { name: "Reject", exact: true }).click();
    await expect(page.getByText("Task rejected")).toBeVisible({
      timeout: 5_000,
    });
  });
});
