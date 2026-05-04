import * as vscode from "vscode";
import type { KaganClient } from "../api/client.js";
import type { BoardTreeProvider } from "../providers/board.tree.js";
import type { AgentOutputProvider } from "../providers/events.output.js";
import type { ReviewCommentProvider } from "../providers/review.comments.js";
import type { TaskScmProvider } from "../providers/tasks.scm.js";
import type { AgentTerminalProvider } from "../providers/tasks.terminal.js";
import type { Priority, UpdateTaskInput, WireTask } from "@kagan/shared-api-client";
import { TASK_COLUMNS } from "@kagan/shared-api-client";
import type { LauncherBackend } from "../api/local.js";
import { confirmAction, resolveTask, type TaskItem, withErrors } from "./common.js";
import { TASK_COLUMN_LABELS } from "../providers/board.tree.helpers.js";
import { describeBackendStatus, sortBackends } from "./settings.js";

const PRIORITIES: Priority[] = ["LOW", "MEDIUM", "HIGH", "CRITICAL"];
const LAUNCHERS: LauncherBackend[] = ["vscode", "cursor", "windsurf", "kiro", "antigravity", "tmux", "nvim"];

interface PickResult<T> {
  cancelled: boolean;
  value: T;
}

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
        if (description === undefined) return;

        const priority = await pickPriority();
        const baseBranch = await vscode.window.showInputBox({
          prompt: "Base branch",
          placeHolder: "Optional target branch, e.g. main",
        });
        if (baseBranch === undefined) return;

        const acceptanceCriteria = await vscode.window.showInputBox({
          prompt: "Acceptance criteria",
          placeHolder: "Optional; separate multiple items with |, e.g. Tests pass | Docs updated",
        });
        if (acceptanceCriteria === undefined) return;

        const agentBackend = await pickAgentBackend(client);
        if (agentBackend.cancelled) return;

        const launcher = await pickLauncher();
        if (launcher.cancelled) return;

        const githubIssue = await pickGithubIssue(client);
        if (githubIssue.cancelled) return;

        await client.createTask({
          title: title.trim(),
          description: description?.trim() || undefined,
          priority: priority ?? undefined,
          base_branch: baseBranch?.trim() || undefined,
          acceptance_criteria: parseAcceptanceCriteria(acceptanceCriteria),
          agent_backend: agentBackend.value,
          launcher: launcher.value ?? undefined,
          github_issue: githubIssue.value,
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
        await vscode.commands.executeCommand("kagan.chat.open", { kind: "task", task: updated });
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

        if ((task.review_verdicts ?? []).length > 0 || task.status === "REVIEW") {
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
        if (description === undefined) return;

        const priority = await pickPriority();
        const baseBranch = await vscode.window.showInputBox({
          prompt: "Base branch",
          value: task.base_branch ?? "",
          placeHolder: "Optional target branch, e.g. main",
        });
        if (baseBranch === undefined) return;

        const acceptanceCriteria = await vscode.window.showInputBox({
          prompt: "Acceptance criteria",
          value: (task.acceptance_criteria ?? []).map((c) => c.text).join(" | "),
          placeHolder: "Optional; separate multiple items with |",
        });
        if (acceptanceCriteria === undefined) return;

        const agentBackend = await pickAgentBackend(client, task.agent_backend);
        if (agentBackend.cancelled) return;

        const launcher = await pickLauncher(task.launcher);
        if (launcher.cancelled) return;

        const update: UpdateTaskInput = {
          title: title.trim(),
          description: description?.trim() || "",
          priority: priority ?? task.priority,
          base_branch: baseBranch?.trim() || undefined,
          acceptance_criteria: parseAcceptanceCriteria(acceptanceCriteria) ?? [],
        };
        if (agentBackend.value) {
          update.agent_backend = agentBackend.value;
        }
        if (launcher.value !== undefined) {
          update.launcher = launcher.value;
        }

        await client.updateTask(task.id, update);
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
    (task.acceptance_criteria ?? []).length > 0
      ? (task.acceptance_criteria ?? []).map((c, i) => `${i + 1}. ${c.text}`).join("\n")
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
    .split(/[|\n]/)
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

async function pickAgentBackend(
  client: KaganClient,
  currentBackend?: string | null,
): Promise<PickResult<string | undefined>> {
  const chatAgents = await client.getChatAgents();
  const backends = sortBackends(chatAgents.backends);

  const picked = await vscode.window.showQuickPick(
    [
      {
        label: currentBackend === undefined ? "Default backend" : "Keep current backend",
        description: currentBackend === undefined
          ? `Server default: ${chatAgents.default}`
          : currentBackend ?? `Default (${chatAgents.default})`,
        value: undefined,
      },
      ...backends.map((backend) => ({
        label: backend.name,
        description: describeBackendStatus(backend, currentBackend ?? chatAgents.default),
        value: backend.name,
      })),
    ],
    {
      placeHolder: currentBackend === undefined
        ? "Select agent backend"
        : "Select agent backend for this task",
    },
  );

  return { cancelled: !picked, value: picked?.value };
}

async function pickLauncher(currentLauncher?: string | null): Promise<PickResult<string | null | undefined>> {
  const picked = await vscode.window.showQuickPick(
    [
      {
        label: currentLauncher === undefined ? "Default launcher" : "Keep current launcher",
        description: currentLauncher === undefined ? "Use server or project default" : currentLauncher ?? "Default",
        value: undefined,
      },
      ...(currentLauncher === undefined
        ? []
        : [{ label: "Default launcher", description: "Clear task-specific launcher", value: null }]),
      ...LAUNCHERS.map((launcher) => ({
        label: launcher,
        description: launcherDescription(launcher),
        value: launcher,
      })),
    ],
    {
      placeHolder: currentLauncher === undefined
        ? "Select launcher"
        : "Select launcher for this task",
    },
  );

  return { cancelled: !picked, value: picked?.value };
}

function launcherDescription(launcher: LauncherBackend): string {
  switch (launcher) {
    case "vscode":
    case "cursor":
    case "windsurf":
    case "kiro":
    case "antigravity":
      return "Attach in editor";
    case "tmux":
      return "Attach in tmux";
    case "nvim":
      return "Attach in Neovim";
  }
}

/**
 * Prompt user to pick a GitHub issue link mode.
 * Returns cancelled=true if user dismissed the picker.
 * Returns value=undefined for "none", "new" for create-new, or "#N" for link.
 * Skips entirely if no GitHub integration is configured (returns cancelled=false, value=undefined).
 */
export async function pickGithubIssue(client: KaganClient): Promise<PickResult<string | undefined>> {
  let hasGithub = false;
  try {
    const result = await client.detectGithubRepo();
    hasGithub = Boolean(result.repo_slug);
  } catch {
    // GitHub integration unavailable — skip silently
    return { cancelled: false, value: undefined };
  }

  if (!hasGithub) {
    return { cancelled: false, value: undefined };
  }

  const picked = await vscode.window.showQuickPick(
    [
      { label: "None", description: "No GitHub issue link", value: undefined },
      { label: "Link to existing issue (#N)", description: "Enter an issue number", value: "__link__" },
      { label: "Create new issue from task", description: "Creates a GitHub issue on submit", value: "new" },
    ],
    { placeHolder: "GitHub issue (optional)" },
  );

  if (!picked) return { cancelled: true, value: undefined };
  if (picked.value === undefined) return { cancelled: false, value: undefined };
  if (picked.value === "new") return { cancelled: false, value: "new" };

  // User wants to link an existing issue — ask for the number
  const numberStr = await vscode.window.showInputBox({
    prompt: "Issue number",
    placeHolder: "e.g. 42",
    validateInput: (v) => {
      const n = Number(v.replace(/^#/, ""));
      if (!Number.isInteger(n) || n <= 0) return "Enter a positive integer";
      return undefined;
    },
  });
  if (numberStr === undefined) return { cancelled: true, value: undefined };
  return { cancelled: false, value: numberStr.replace(/^#/, "") };
}
