// Consolidated task UI journey: routing, edit dialogs, run controls, sessions,
// review / approve, noop lifecycle, and unknown-task empty state.
import { expect, test, type APIRequestContext } from "./coverage-fixture";
import {
  createTaskAndRun,
  createTaskAndRunWithScenario,
  createTaskViaApi,
  ensureBoardReady,
  ensureProjectReady,
  reviewGate,
  scheduleScenario,
  waitForTaskSessions,
  waitForTaskStatus,
} from "./helpers";

type WireEnvelope<T> = { ok: boolean; data?: T };

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
  const envelope = (await created.json()) as WireEnvelope<{ id: string }>;
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

test.describe("Task journey", () => {
  test.describe.configure({ timeout: 240_000 });

  test("routing, edits, agent run, review, and noop lifecycle", async ({
    page,
    request,
  }) => {
    await test.step("seed board", async () => {
      await ensureBoardReady(page, request);
    });

    await test.step("unknown task id shows empty state copy", async () => {
      await page.goto("/task/non-existent-deadbeef");
      await page.waitForLoadState("load");

      await expect(page.getByRole("heading", { name: /Task not found/i })).toBeVisible({
        timeout: 20_000,
      });
      await expect(
        page.getByText(/may have been deleted|no longer synced/i),
      ).toBeVisible();
    });

    await test.step("overview tab defaults for backlog task", async () => {
      const taskId = await createTaskViaApi(request, `Overview esc ${Date.now()}`);

      await page.goto(`/task/${taskId}`);
      await page.waitForLoadState("load");

      await expect(page.getByRole("tab", { name: "Overview" })).toHaveAttribute(
        "data-state",
        "active",
      );

      await page.goto("/board");
      await page.waitForLoadState("load");
      await expect(
        page.getByRole("heading", { name: "Backlog", exact: true }),
      ).toBeVisible();
    });

    await test.step("edit title from detail via keyboard", async () => {
      const title = `Edit me ${Date.now()}`;
      const taskId = await createTaskViaApi(request, title);

      await page.goto(`/task/${taskId}`);
      await page.waitForLoadState("load");

      await page.locator("h1").first().click();
      await page.keyboard.press("e");

      const dialog = page.getByRole("dialog", { name: "Edit Task" });
      await expect(dialog).toBeVisible();

      const newTitle = `Edited ${Date.now()}`;
      await dialog.getByLabel("Title").fill(newTitle);
      await dialog.getByRole("button", { name: "Save" }).click();
      await expect(dialog).toBeHidden();

      await page.reload();
      await page.waitForLoadState("load");
      await expect(page.getByRole("heading", { name: newTitle })).toBeVisible();
    });

    await test.step("edit description and cancel paths", async () => {
      const title = `Desc edit ${Date.now()}`;
      const taskId = await createTaskViaApi(request, title);

      await page.goto(`/task/${taskId}`);
      await page.waitForLoadState("load");

      await page.locator("h1").first().click();
      await page.keyboard.press("e");
      let dialog = page.getByRole("dialog", { name: "Edit Task" });
      await expect(dialog).toBeVisible();

      const newDesc = "This is the updated description.";
      await dialog.getByLabel("Description").fill(newDesc);
      await dialog.getByRole("button", { name: "Save" }).click();
      await expect(dialog).toBeHidden();

      await page.reload();
      await page.waitForLoadState("load");
      await expect(page.getByText(newDesc)).toBeVisible();

      await page.locator("h1").first().click();
      await page.keyboard.press("e");
      dialog = page.getByRole("dialog", { name: "Edit Task" });
      await expect(dialog).toBeVisible();
      await dialog.getByLabel("Title").fill("Should not save");
      await dialog.getByRole("button", { name: "Cancel" }).click();
      await expect(dialog).toBeHidden();

      await page.reload();
      await page.waitForLoadState("load");
      await expect(page.getByRole("heading", { name: title })).toBeVisible();
      await expect(page.getByText("Should not save")).toHaveCount(0);
    });

    await test.step("Start reaches IN_PROGRESS with Stop and Open chat", async () => {
      const title = `RunControl ${Date.now()}`;
      const taskId = await createTaskViaApi(request, title);

      await page.goto(`/task/${taskId}`);
      await page.waitForLoadState("load");

      await page.getByRole("button", { name: "Start", exact: true }).click();
      await waitForTaskStatus(request, taskId, "IN_PROGRESS", { timeoutMs: 15_000 });
      await expect(page.getByRole("button", { name: "Stop" })).toBeVisible();
      await waitForTaskSessions(request, taskId);

      await expect(
        page.getByRole("button", { name: "Open session chat" }),
      ).toBeVisible({ timeout: 10_000 });
    });

    await test.step("Changes tab shows empty diff while fake-agent run is active", async () => {
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
      await expect(page.getByText("No code changes yet")).toBeVisible();
    });

    await test.step("adaptive Review tab and approve lands in Done", async () => {
      const adaptiveTitle = `Adaptive ${Date.now()}`;
      const adaptiveId = await createTaskAndRunWithScenario(request, adaptiveTitle, (id) =>
        reviewGate(id, "feat.md", "# Hello"),
      );
      await waitForTaskStatus(request, adaptiveId, "REVIEW", { timeoutMs: 15_000 });

      await page.goto(`/task/${adaptiveId}`);
      await page.waitForLoadState("load");

      await expect(page.getByRole("tab", { name: "Review" })).toHaveAttribute(
        "data-state",
        "active",
      );

      const reviewTitle = `Review panel ${Date.now()}`;
      const reviewId = await createReviewTask(request, reviewTitle, [
        "Code follows style guide",
        "Tests pass",
      ]);

      await page.goto(`/task/${reviewId}`);
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

      await page.getByRole("button", { name: "Approve", exact: true }).click();
      await expect(page.getByText("Task approved")).toBeVisible({
        timeout: 5_000,
      });

      const rejectTitle = `Reject test ${Date.now()}`;
      const rejectId = await createReviewTask(request, rejectTitle);

      await page.goto(`/task/${rejectId}`);
      await page.waitForLoadState("load");

      const feedbackText = "Needs more tests";
      await page.locator('textarea[placeholder="Optional feedback..."]').fill(feedbackText);
      await page.getByRole("button", { name: "Reject", exact: true }).click();
      await expect(page.getByText("Task rejected")).toBeVisible({
        timeout: 5_000,
      });
    });

    await test.step("review-gate task appears in Review column; noop returns to Backlog", async () => {
      const reviewGateTitle = `Review gate ${Date.now()}`;
      const rgId = await createTaskAndRunWithScenario(request, reviewGateTitle, (id) =>
        reviewGate(id, "feature.md", "# New Feature\n"),
      );
      await waitForTaskStatus(request, rgId, "REVIEW", { timeoutMs: 15_000 });

      await page.goto("/board");
      await page.waitForLoadState("load");

      await expect(
        page.getByRole("region", { name: /Review/ }).getByRole("button", { name: reviewGateTitle }),
      ).toBeVisible({ timeout: 10_000 });

      const noopTitle = `Noop ${Date.now()}`;
      const noopId = await createTaskAndRun(request, noopTitle);
      await waitForTaskStatus(request, noopId, "BACKLOG", { timeoutMs: 20_000 });

      await page.goto("/board");
      await page.waitForLoadState("load");

      await expect(
        page.getByRole("region", { name: /Backlog/ }).getByRole("button", { name: noopTitle }),
      ).toBeVisible({ timeout: 10_000 });
    });
  });
});
