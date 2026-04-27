import * as vscode from "vscode";
import type { KaganClient } from "../api/client.js";
import type { BoardTreeProvider } from "../providers/board.tree.js";
import type { ReviewCommentProvider } from "../providers/review.comments.js";
import { confirmAction, resolveTask, type TaskItem, withErrors } from "./common.js";

const REVIEW_RESOLVE_OPTIONS = {
  status: "REVIEW",
  noMatchesMessage: "No tasks are waiting for review.",
  placeHolder: "Select a review task",
  showStatusAndPriority: false,
} as const;

export function registerReviewCommands(
  context: vscode.ExtensionContext,
  client: KaganClient,
  boardProvider: BoardTreeProvider,
  reviewProvider: ReviewCommentProvider,
): void {
  context.subscriptions.push(
    vscode.commands.registerCommand("kagan.review.approve", async (item?: TaskItem) => {
      await withErrors("approve task", async () => {
        const task = await resolveTask(client, item, REVIEW_RESOLVE_OPTIONS);
        if (!task) return;

        const result = await client.reviewDecide(task.id, { action: "approve" });
        boardProvider.refresh();

        if (result.task) {
          await reviewProvider.showTaskReview(result.task);
        }
      });
    }),

    vscode.commands.registerCommand("kagan.review.reject", async (item?: TaskItem) => {
      await withErrors("reject task", async () => {
        const task = await resolveTask(client, item, REVIEW_RESOLVE_OPTIONS);
        if (!task) return;

        const feedback = await vscode.window.showInputBox({
          prompt: "Why should this task be rejected?",
          validateInput: (value) => (value.trim() ? undefined : "Feedback is required"),
        });
        if (!feedback) return;

        const result = await client.reviewDecide(task.id, {
          action: "reject",
          feedback: feedback.trim(),
        });
        boardProvider.refresh();

        if (result.task) {
          await reviewProvider.showTaskReview(result.task);
        }
      });
    }),

    vscode.commands.registerCommand("kagan.review.merge", async (item?: TaskItem) => {
      await withErrors("merge task", async () => {
        const task = await resolveTask(client, item, REVIEW_RESOLVE_OPTIONS);
        if (!task) return;

        const confirmed = await confirmAction(
          `Merge "${task.title}" into ${task.base_branch ?? "base branch"}?`,
          "Merge Task",
        );
        if (!confirmed) return;

        await client.reviewDecide(task.id, { action: "merge" });
        boardProvider.refresh();
        reviewProvider.clear();
      });
    }),
  );
}
