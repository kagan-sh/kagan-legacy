import * as vscode from "vscode";
import type { KaganClient } from "../api/client.js";
import type { BoardTreeProvider } from "../providers/board.tree.js";
import type { AgentOutputProvider } from "../providers/events.output.js";
import type { ReviewCommentProvider } from "../providers/review.comments.js";
import type { TaskScmProvider } from "../providers/tasks.scm.js";
import type { AgentTerminalProvider } from "../providers/tasks.terminal.js";
import type { Priority, WireTask } from "../api/types.js";
import { TASK_COLUMNS } from "../api/types.js";
import { confirmAction, resolveTask, type TaskItem, withErrors } from "./common.js";
import { TASK_COLUMN_LABELS } from "../providers/board.tree.helpers.js";

const PRIORITIES: Priority[] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];

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
        const baseBranch = await vscode.window.showInputBox({
          prompt: "Base branch",
          placeHolder: "Optional target branch, e.g. main",
        });
        const acceptanceCriteria = await vscode.window.showInputBox({
          prompt: "Acceptance criteria",
          placeHolder: "Optional; separate multiple items with |",
        });
        const agentBackend = await vscode.window.showInputBox({
          prompt: "Agent backend",
          placeHolder: "Optional; leave blank to use the default backend",
        });

        await client.createTask({
          title: title.trim(),
          description: description?.trim() || undefined,
          priority: priority ?? undefined,
          base_branch: baseBranch?.trim() || undefined,
          acceptance_criteria: parseAcceptanceCriteria(acceptanceCriteria),
          agent_backend: agentBackend?.trim() || undefined,
        });
        boardProvider.refresh();
      });
    }),

    vscode.commands.registerCommand("kagan.task.run", async (item?: TaskItem) => {
      await withErrors("run task", async () => {
        const task = await resolveTask(client, item, { status: "BACKLOG" });
        if (!task) return;

        const updated = await client.runTask(task.id);
        boardProvider.refresh();
        await outputProvider.showTask(updated);
      });
    }),

    vscode.commands.registerCommand("kagan.task.cancel", async (item?: TaskItem) => {
      await withErrors("cancel task", async () => {
        const task = await resolveTask(client, item, { status: "IN_PROGRESS" });
        if (!task) return;

        const confirmed = await confirmAction(
          `Cancel "${task.title}"?`,
          "Cancel Task",
        );
        if (!confirmed) return;

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

        const confirmed = await confirmAction(
          `Delete "${task.title}"?`,
          "Delete Task",
        );
        if (!confirmed) return;

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
            label: TASK_COLUMN_LABELS[status],
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
        const task = await resolveTask(client, item, { status: "IN_PROGRESS" });
        if (!task) return;
        await terminalProvider.attachToTask(task);
      });
    }),
  );
}

function renderTaskSummary(task: WireTask): string {
  const criteria =
    task.acceptance_criteria.length > 0
      ? task.acceptance_criteria.map((c) => `${c.ordinal + 1}. ${c.text}`).join("\n")
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

function parseAcceptanceCriteria(value: string | undefined): string[] | undefined {
  if (!value) return undefined;
  const items = value
    .split("|")
    .map((item) => item.trim())
    .filter(Boolean);
  return items.length > 0 ? items : undefined;
}

async function pickPriority(): Promise<Priority | undefined> {
  const picked = await vscode.window.showQuickPick(
    PRIORITIES.map((priority) => ({ label: priority, priority })),
    { placeHolder: "Priority" },
  );
  return picked?.priority;
}
