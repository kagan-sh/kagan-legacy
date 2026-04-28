import * as vscode from "vscode";
import type { KaganClient } from "../api/client.js";
import type { TaskStatus, WireTask } from "../api/types.js";
import type { BoardItem } from "../providers/board.tree.js";

export type TaskItem = Extract<BoardItem, { kind: "task" }>;

export interface TaskPickItem {
  label: string;
  description?: string;
  detail?: string;
  task: WireTask;
}

interface ResolveTaskOptions {
  status?: TaskStatus;
  noMatchesMessage?: string;
  placeHolder?: string;
  showStatusAndPriority?: boolean;
}

export function isTaskItem(item: unknown): item is TaskItem {
  return (
    typeof item === "object" &&
    item !== null &&
    (item as { kind?: unknown }).kind === "task"
  );
}

export function taskPickItems(
  tasks: WireTask[],
  { showStatusAndPriority = true }: Pick<ResolveTaskOptions, "showStatusAndPriority"> = {},
): TaskPickItem[] {
  return tasks.map((task) => ({
    label: task.title,
    description: showStatusAndPriority ? `${task.status} · ${task.priority}` : undefined,
    detail: task.description || undefined,
    task,
  }));
}

export async function resolveTask(
  client: KaganClient,
  item?: TaskItem,
  {
    status,
    noMatchesMessage = "No matching tasks found.",
    placeHolder = "Select a task",
    showStatusAndPriority = true,
  }: ResolveTaskOptions = {},
): Promise<WireTask | undefined> {
  if (isTaskItem(item)) {
    return client.getTask(item.task.id);
  }

  const tasks = await client.getTasks(status);
  if (tasks.length === 0) {
    vscode.window.showInformationMessage(noMatchesMessage);
    return undefined;
  }

  const picked = await vscode.window.showQuickPick(
    taskPickItems(tasks, { showStatusAndPriority }),
    { placeHolder },
  );
  return picked?.task;
}

export async function confirmAction(message: string, action: string): Promise<boolean> {
  const confirmed = await vscode.window.showWarningMessage(message, { modal: true }, action);
  return confirmed === action;
}

export function formatCommandError(action: string, error: unknown): string {
  const message = error instanceof Error ? error.message : String(error);
  return `Failed to ${action}: ${message}`;
}

export async function withErrors(action: string, run: () => Promise<void>): Promise<void> {
  try {
    await run();
  } catch (error) {
    vscode.window.showErrorMessage(formatCommandError(action, error));
  }
}
