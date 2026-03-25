import * as vscode from "vscode";
import type { KaganClient } from "../api/client.js";
import type { BoardItem, BoardTreeProvider } from "../providers/board.tree.js";
import type { AgentOutputProvider } from "../providers/events.output.js";
import type { ReviewCommentProvider } from "../providers/review.comments.js";
import type { TaskScmProvider } from "../providers/tasks.scm.js";
import type { AgentTerminalProvider } from "../providers/tasks.terminal.js";
import type { Priority, TaskStatus, WireTask } from "../api/types.js";
import { TASK_COLUMNS } from "../api/types.js";

type TaskItem = Extract<BoardItem, { kind: "task" }>;

const PRIORITIES: Priority[] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];

const COLUMN_LABELS: Record<TaskStatus, string> = {
  BACKLOG: "Backlog",
  IN_PROGRESS: "In Progress",
  REVIEW: "Review",
  DONE: "Done",
};

export function registerTaskCommands(
  context: vscode.ExtensionContext,
  client: KaganClient,
  boardProvider: BoardTreeProvider,
  outputProvider: AgentOutputProvider,
  scmProvider: TaskScmProvider,
  reviewProvider: ReviewCommentProvider,
  terminalProvider: AgentTerminalProvider,
): void {
  context.subscriptions.push(
    vscode.commands.registerCommand("kagan.task.create", async () => {
      await withErrors("create task", async () => {
        const title = await vscode.window.showInputBox({
          prompt: "Task title",
          placeHolder: "What needs to be done?",
          validateInput: (value) => (value.trim() ? undefined : "Title is required"),
        });
        if (!title) return;

        const description = await vscode.window.showInputBox({
          prompt: "Description",
          placeHolder: "Optional context for the task",
        });

        const priority = await pickPriority();

        await client.createTask({
          title: title.trim(),
          description: description?.trim() || undefined,
          priority: priority ?? undefined,
        });
        boardProvider.refresh();
      });
    }),

    vscode.commands.registerCommand("kagan.task.run", async (item?: TaskItem) => {
      await withErrors("run task", async () => {
        const task = await resolveTask(client, item, "BACKLOG");
        if (!task) return;

        const updated = await client.runTask(task.id);
        boardProvider.refresh();
        await outputProvider.showTask(updated);
      });
    }),

    vscode.commands.registerCommand("kagan.task.cancel", async (item?: TaskItem) => {
      await withErrors("cancel task", async () => {
        const task = await resolveTask(client, item, "IN_PROGRESS");
        if (!task) return;

        const confirmed = await vscode.window.showWarningMessage(
          `Cancel "${task.title}"?`,
          { modal: true },
          "Cancel Task",
        );
        if (confirmed !== "Cancel Task") return;

        await client.cancelTask(task.id);
        boardProvider.refresh();
      });
    }),

    vscode.commands.registerCommand("kagan.task.open", async (item?: TaskItem) => {
      await withErrors("open task", async () => {
        const task = await resolveTask(client, item);
        if (!task) return;

        if (task.review_verdicts.length > 0 || task.status === "REVIEW") {
          await reviewProvider.showTaskReview(task);
          return;
        }

        const document = await vscode.workspace.openTextDocument({
          language: "markdown",
          content: renderTaskSummary(task),
        });
        await vscode.window.showTextDocument(document, { preview: false });
      });
    }),

    vscode.commands.registerCommand("kagan.task.delete", async (item?: TaskItem) => {
      await withErrors("delete task", async () => {
        const task = await resolveTask(client, item);
        if (!task) return;

        const confirmed = await vscode.window.showWarningMessage(
          `Delete "${task.title}"?`,
          { modal: true },
          "Delete Task",
        );
        if (confirmed !== "Delete Task") return;

        await client.deleteTask(task.id);
        boardProvider.refresh();
      });
    }),

    vscode.commands.registerCommand("kagan.task.move", async (item?: TaskItem) => {
      await withErrors("move task", async () => {
        const task = await resolveTask(client, item);
        if (!task) return;

        const picked = await vscode.window.showQuickPick(
          TASK_COLUMNS.map((status) => ({
            label: COLUMN_LABELS[status],
            description: status === task.status ? "Current" : undefined,
            status,
          })),
          { placeHolder: `Move "${task.title}" to` },
        );
        if (!picked || picked.status === task.status) return;

        await client.transitionStatus(task.id, picked.status);
        boardProvider.refresh();
      });
    }),

    vscode.commands.registerCommand("kagan.task.edit", async (item?: TaskItem) => {
      await withErrors("edit task", async () => {
        const task = await resolveTask(client, item);
        if (!task) return;

        const title = await vscode.window.showInputBox({
          prompt: "Title",
          value: task.title,
          validateInput: (value) => (value.trim() ? undefined : "Title is required"),
        });
        if (!title) return;

        const description = await vscode.window.showInputBox({
          prompt: "Description",
          value: task.description,
        });

        const priority = await pickPriority();

        await client.updateTask(task.id, {
          title: title.trim(),
          description: description?.trim() || "",
          priority: priority ?? task.priority,
        });
        boardProvider.refresh();
      });
    }),

    vscode.commands.registerCommand("kagan.task.diff", async (item?: TaskItem) => {
      await withErrors("show task diff", async () => {
        const task = await resolveTask(client, item);
        if (!task) return;
        await scmProvider.showTaskDiff(task);
      });
    }),

    vscode.commands.registerCommand("kagan.events.show", async (item?: TaskItem) => {
      await withErrors("show agent output", async () => {
        const task = await resolveTask(client, item);
        if (!task) return;
        await outputProvider.showTask(task);
      });
    }),

    vscode.commands.registerCommand("kagan.terminal.attach", async (item?: TaskItem) => {
      await withErrors("attach terminal", async () => {
        const task = await resolveTask(client, item, "IN_PROGRESS");
        if (!task) return;
        await terminalProvider.attachToTask(task);
      });
    }),
  );
}

function isTaskItem(item: unknown): item is TaskItem {
  return typeof item === "object" && item !== null && "kind" in item && (item as TaskItem).kind === "task";
}

async function resolveTask(
  client: KaganClient,
  item?: TaskItem,
  status?: TaskStatus,
): Promise<WireTask | undefined> {
  if (isTaskItem(item)) {
    return client.getTask(item.task.id);
  }

  const tasks = await client.getTasks(status);
  if (tasks.length === 0) {
    vscode.window.showInformationMessage("No matching tasks found.");
    return undefined;
  }

  const picked = await vscode.window.showQuickPick(
    tasks.map((task) => ({
      label: task.title,
      description: `${task.status} · ${task.priority}`,
      detail: task.description || undefined,
      task,
    })),
    { placeHolder: "Select a task" },
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

function renderTaskSummary(task: WireTask): string {
  const criteria =
    task.acceptance_criteria.length > 0
      ? task.acceptance_criteria.map((item, index) => `${index + 1}. ${item}`).join("\n")
      : "None";

  return [
    `# ${task.title}`,
    "",
    `- ID: ${task.id}`,
    `- Status: ${task.status}`,
    `- Priority: ${task.priority}`,
    `- Agent: ${task.agent_backend ?? "Default"}`,
    `- Launcher: ${task.launcher ?? "Default"}`,
    "",
    "## Description",
    "",
    task.description || "No description",
    "",
    "## Acceptance Criteria",
    "",
    criteria,
  ].join("\n");
}

async function pickPriority(): Promise<Priority | undefined> {
  const picked = await vscode.window.showQuickPick(
    PRIORITIES.map((priority) => ({ label: priority, priority })),
    { placeHolder: "Priority" },
  );
  return picked?.priority;
}
