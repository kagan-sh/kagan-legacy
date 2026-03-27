// Kanban board as a VS Code tree view.
// "Flat is better than nested." — two item kinds, one provider, no inheritance.

import * as vscode from "vscode";
import type { KaganClient } from "../api/client.js";
import {
  TASK_COLUMNS,
  PRIORITY_ICONS,
  STATUS_ICONS,
  SSE_TYPE,
  type WireTask,
  type TaskStatus,
  type SSEMessage,
} from "../api/types.js";

// ── Item types ──────────────────────────────────────────────────────────────

interface ColumnItem {
  kind: "column";
  status: TaskStatus;
  count: number;
}

interface TaskItem {
  kind: "task";
  task: WireTask;
}

export type BoardItem = ColumnItem | TaskItem;

// ── Column labels ───────────────────────────────────────────────────────────

const COLUMN_LABELS: Record<TaskStatus, string> = {
  BACKLOG: "Backlog",
  IN_PROGRESS: "In Progress",
  REVIEW: "Review",
  DONE: "Done",
};

// ── Provider ────────────────────────────────────────────────────────────────

export class BoardTreeProvider implements vscode.TreeDataProvider<BoardItem> {
  private readonly _onDidChangeTreeData = new vscode.EventEmitter<BoardItem | undefined>();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private tasksByStatus = new Map<TaskStatus, WireTask[]>();

  constructor(private readonly client: KaganClient) {}

  refresh(): void {
    this.tasksByStatus.clear();
    this._onDidChangeTreeData.fire(undefined);
  }

  onSSE(msg: SSEMessage): void {
    if (msg.type === SSE_TYPE.TASK_UPDATED || msg.type === SSE_TYPE.SESSION_EVENT) this.refresh();
  }

  // ── TreeDataProvider ────────────────────────────────────────────────────

  async getChildren(element?: BoardItem): Promise<BoardItem[]> {
    if (!element) {
      return this.getRootColumns();
    }
    if (element.kind === "column") {
      return this.getColumnTasks(element.status);
    }
    return [];
  }

  getTreeItem(element: BoardItem): vscode.TreeItem {
    if (element.kind === "column") {
      return this.buildColumnItem(element);
    }
    return this.buildTaskItem(element);
  }

  // ── Root columns ──────────────────────────────────────────────────────

  private async getRootColumns(): Promise<ColumnItem[]> {
    const tasks = await this.fetchAllTasks();
    return TASK_COLUMNS.map((status) => ({
      kind: "column" as const,
      status,
      count: tasks.filter((t) => t.status === status).length,
    }));
  }

  // ── Column children ───────────────────────────────────────────────────

  private async getColumnTasks(status: TaskStatus): Promise<TaskItem[]> {
    const cached = this.tasksByStatus.get(status);
    const tasks = cached ?? (await this.fetchTasksByStatus(status));
    return tasks.map((task) => ({ kind: "task" as const, task }));
  }

  // ── Tree item builders ────────────────────────────────────────────────

  private buildColumnItem(column: ColumnItem): vscode.TreeItem {
    const label = `${COLUMN_LABELS[column.status]} (${column.count})`;
    const state =
      column.count > 0
        ? vscode.TreeItemCollapsibleState.Expanded
        : vscode.TreeItemCollapsibleState.Collapsed;

    const item = new vscode.TreeItem(label, state);
    item.iconPath = new vscode.ThemeIcon(STATUS_ICONS[column.status]);
    item.contextValue = `column.${column.status}`;
    return item;
  }

  private buildTaskItem(element: TaskItem): vscode.TreeItem {
    const { task } = element;

    const item = new vscode.TreeItem(task.title, vscode.TreeItemCollapsibleState.None);
    item.iconPath = new vscode.ThemeIcon(PRIORITY_ICONS[task.priority]);
    item.contextValue = `task.${task.status}`;
    item.tooltip = this.buildTooltip(task);
    item.description = this.buildDescription(task);
    item.command = {
      title: "Open Task",
      command: "kagan.task.open",
      arguments: [element],
    };

    return item;
  }

  private buildDescription(task: WireTask): string {
    const parts: string[] = [];

    if (task.status === "IN_PROGRESS" && task.active_session) {
      parts.push(`$(sync~spin) ${task.active_session.agent_backend}`);
    } else if (task.agent_backend) {
      parts.push(task.agent_backend);
    }

    return parts.join(" ");
  }

  private buildTooltip(task: WireTask): string {
    const lines = [task.title];
    if (task.description) lines.push(task.description);
    if (task.agent_backend) lines.push(`Agent: ${task.agent_backend}`);
    if (task.active_session) lines.push(`Session: ${task.active_session.status}`);
    return lines.join("\n");
  }

  // ── Data fetching ─────────────────────────────────────────────────────

  private async fetchAllTasks(): Promise<WireTask[]> {
    try {
      const tasks = await this.client.getTasks();
      this.tasksByStatus.clear();
      for (const status of TASK_COLUMNS) {
        this.tasksByStatus.set(
          status,
          tasks.filter((t) => t.status === status),
        );
      }
      return tasks;
    } catch {
      vscode.window.showErrorMessage("Kagan: Failed to load tasks");
      return [];
    }
  }

  private async fetchTasksByStatus(status: TaskStatus): Promise<WireTask[]> {
    try {
      const tasks = await this.client.getTasks(status);
      const sorted = [...tasks].sort((left, right) => left.title.localeCompare(right.title));
      this.tasksByStatus.set(status, sorted);
      return sorted;
    } catch {
      vscode.window.showErrorMessage("Kagan: Failed to load tasks");
      return [];
    }
  }
}
