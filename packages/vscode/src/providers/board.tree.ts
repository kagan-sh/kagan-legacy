// Kanban board as a VS Code tree view.
// "Flat is better than nested." — two item kinds, one provider, no inheritance.

import * as vscode from "vscode";
import type { KaganClient } from "../api/client.js";
import {
  TASK_COLUMNS,
  SSE_TYPE,
  type WireTask,
  type TaskStatus,
  type Priority,
  type SSEMessage,
} from "@kagan/shared-api-client";
import { PRIORITY_ICONS, STATUS_ICONS } from "../api/local.js";
import { groupTasksByStatus, sortTasksByTitle, TASK_COLUMN_LABELS } from "./board.tree.helpers.js";

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
    // Only refresh on TASK_UPDATED — SESSION_EVENT is internal agent output (no tree change).
    if (msg.type === SSE_TYPE.TASK_UPDATED) this.refresh();
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
    await this.fetchAllTasks();
    return TASK_COLUMNS.map((status) => ({
      kind: "column" as const,
      status,
      count: this.tasksByStatus.get(status)?.length ?? 0,
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
    const label = `${TASK_COLUMN_LABELS[column.status]} (${column.count})`;
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
    item.iconPath = new vscode.ThemeIcon(PRIORITY_ICONS[task.priority as Priority] ?? "dash");
    item.contextValue = `task.${task.status}`;
    item.tooltip = this.buildTooltip(task);
    item.description = this.buildDescription(task);
    item.command = {
      title: "Open task",
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
    if (task.active_session) lines.push(`Session status: ${task.active_session.status}`);
    return lines.join("\n");
  }

  // ── Data fetching ─────────────────────────────────────────────────────

  private async safeFetch<T>(fn: () => Promise<T>, fallback: T): Promise<T> {
    try {
      return await fn();
    } catch {
      vscode.window.showErrorMessage("Kagan: Failed to load tasks");
      return fallback;
    }
  }

  private async fetchAllTasks(): Promise<WireTask[]> {
    return this.safeFetch(async () => {
      const tasks = await this.client.getTasks();
      this.tasksByStatus = groupTasksByStatus(tasks);
      return tasks;
    }, []);
  }

  private async fetchTasksByStatus(status: TaskStatus): Promise<WireTask[]> {
    return this.safeFetch(async () => {
      const tasks = await this.client.getTasks(status);
      const sorted = sortTasksByTitle(tasks);
      this.tasksByStatus.set(status, sorted);
      return sorted;
    }, []);
  }
}
