import * as vscode from "vscode";
import type { KaganClient } from "../api/client.js";
import type { BoardItem, BoardTreeProvider } from "../providers/board.tree.js";
import type { ReviewCommentProvider } from "../providers/review.comments.js";
import type { WireTask } from "../api/types.js";

type TaskItem = Extract<BoardItem, { kind: "task" }>;

export function registerReviewCommands(
  context: vscode.ExtensionContext,
  client: KaganClient,
  boardProvider: BoardTreeProvider,
  reviewProvider: ReviewCommentProvider,
): void {
  context.subscriptions.push(
    vscode.commands.registerCommand("kagan.review.approve", async (item?: TaskItem) => {
      await withErrors("approve task", async () => {
        const task = await resolveReviewTask(client, item);
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
        const task = await resolveReviewTask(client, item);
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
        const task = await resolveReviewTask(client, item);
        if (!task) return;

        const confirmed = await vscode.window.showWarningMessage(
          `Merge "${task.title}" into ${task.base_branch ?? "base branch"}?`,
          { modal: true },
          "Merge Task",
        );
        if (confirmed !== "Merge Task") return;

        await client.reviewDecide(task.id, { action: "merge" });
        boardProvider.refresh();
        reviewProvider.clear();
      });
    }),
  );
}

function isTaskItem(item: unknown): item is TaskItem {
  return typeof item === "object" && item !== null && "kind" in item && (item as TaskItem).kind === "task";
}

async function resolveReviewTask(
  client: KaganClient,
  item?: TaskItem,
): Promise<WireTask | undefined> {
  if (isTaskItem(item)) {
    return client.getTask(item.task.id);
  }

  const tasks = await client.getTasks("REVIEW");
  if (tasks.length === 0) {
    vscode.window.showInformationMessage("No tasks are waiting for review.");
    return undefined;
  }

  const picked = await vscode.window.showQuickPick(
    tasks.map((task) => ({
      label: task.title,
      detail: task.description || undefined,
      task,
    })),
    { placeHolder: "Select a review task" },
  );
  return picked?.task;
}

async function withErrors(action: string, run: () => Promise<void>): Promise<void> {
  try {
    await run();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    vscode.window.showErrorMessage(`Failed to ${action}: ${message}`);
  }
}
