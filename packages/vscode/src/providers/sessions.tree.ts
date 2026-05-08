/**
 * SessionsTreeProvider — VS Code tree view listing all unified sessions
 * (orchestrator, general, task worker, task reviewer).
 *
 * Poll interval: 5 s.
 * Click on a node runs `kagan.switchSession <session-id>`.
 */

import * as vscode from "vscode";
import type { KaganClient } from "../api/client.js";
import type { SessionItemResponse } from "@kagan/shared-api-client";

// ── Tree item ────────────────────────────────────────────────────────────────

export type SessionTreeItem =
  | { kind: "header"; label: string }
  | { kind: "session"; session: SessionItemResponse };

// ── Provider ─────────────────────────────────────────────────────────────────

export class SessionsTreeProvider
  implements vscode.TreeDataProvider<SessionTreeItem>, vscode.Disposable
{
  private readonly _onDidChangeTreeData = new vscode.EventEmitter<
    SessionTreeItem | undefined
  >();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private sessions: SessionItemResponse[] = [];
  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private disposed = false;

  constructor(private readonly client: KaganClient) {
    this.pollTimer = setInterval(() => void this.refresh(), 5_000);
  }

  /** Force a refresh — also called when the board SSE fires TASK_UPDATED. */
  refresh(): void {
    void (async () => {
      try {
        const response = await this.client.getSessions();
        if (this.disposed) return;
        this.sessions = response.sessions;
        this._onDidChangeTreeData.fire(undefined);
      } catch {
        // Best-effort — tree stays stale; background poll will retry.
      }
    })();
  }

  getTreeItem(element: SessionTreeItem): vscode.TreeItem {
    if (element.kind === "header") {
      const item = new vscode.TreeItem(
        element.label,
        vscode.TreeItemCollapsibleState.None,
      );
      item.contextValue = "sessionsHeader";
      return item;
    }

    const { session } = element;
    const { label, icon, description } = formatSession(session);

    const item = new vscode.TreeItem(
      label,
      vscode.TreeItemCollapsibleState.None,
    );
    item.description = description;
    item.tooltip = `ID: ${session.id}\nType: ${session.type}\nStatus: ${session.status}\nBackend: ${session.backend ?? "—"}`;
    item.iconPath = new vscode.ThemeIcon(icon);

    const stopBit = session.capabilities.can_stop ? "1" : "0";
    const closeBit = session.capabilities.can_close ? "1" : "0";
    const rolePart = session.role ?? "none";
    item.contextValue = `session.${session.type}.${rolePart}.stop_${stopBit}.close_${closeBit}`;

    item.command = {
      command: "kagan.switchSession",
      title: "Switch to Session",
      arguments: [session.id],
    };
    return item;
  }

  getChildren(element?: SessionTreeItem): SessionTreeItem[] {
    // Root level
    if (!element) {
      if (this.sessions.length === 0) {
        return [{ kind: "header", label: "No sessions" }];
      }
      return this.sessions.map((session) => ({ kind: "session", session }));
    }
    return [];
  }

  dispose(): void {
    this.disposed = true;
    if (this.pollTimer !== null) {
      clearInterval(this.pollTimer);
      this.pollTimer = null;
    }
    this._onDidChangeTreeData.dispose();
  }
}

// ── Formatters ───────────────────────────────────────────────────────────────

function formatSession(session: SessionItemResponse): {
  label: string;
  icon: string;
  description: string;
} {
  const status = session.status;

  switch (session.type) {
    case "orchestrator":
      return {
        label: `◆ ${session.title}`,
        icon: "dashboard",
        description: status,
      };
    case "general":
      return {
        label: `◇ ${session.title}`,
        icon: "comment",
        description: `${session.backend ?? "—"} · ${status}`,
      };
    case "task": {
      const role = session.role ?? "worker";
      const symbol = role === "reviewer" ? "◈" : "▶";
      return {
        label: `${symbol} ${session.title}`,
        icon: role === "reviewer" ? "eye" : "play",
        description: `${role} · ${status}`,
      };
    }
    default:
      return {
        label: session.title,
        icon: "circle-outline",
        description: status,
      };
  }
}
