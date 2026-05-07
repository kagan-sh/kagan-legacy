/**
 * RunningAgentsTreeProvider — VS Code tree view listing active worker and
 * reviewer agent sessions across the workspace project.
 *
 * Poll interval: 5 s (no SSE subscription yet — SSE is global in SSEStream).
 * Click on a node runs `@kagan /attach <session-id>`.
 */

import * as vscode from "vscode";
import type { KaganClient } from "../api/client.js";
import type { ActiveAgentRowResponse } from "@kagan/shared-api-client";

// ── Tree item ────────────────────────────────────────────────────────────────

export type RunningAgentItem =
  | { kind: "header"; label: string }
  | { kind: "agent"; agent: ActiveAgentRowResponse };

// ── Provider ─────────────────────────────────────────────────────────────────

export class RunningAgentsTreeProvider
  implements vscode.TreeDataProvider<RunningAgentItem>, vscode.Disposable
{
  private readonly _onDidChangeTreeData = new vscode.EventEmitter<
    RunningAgentItem | undefined
  >();
  readonly onDidChangeTreeData = this._onDidChangeTreeData.event;

  private agents: ActiveAgentRowResponse[] = [];
  private pollTimer: ReturnType<typeof setInterval> | null = null;
  private disposed = false;

  constructor(private readonly client: KaganClient) {
    this.pollTimer = setInterval(() => void this.refresh(), 5_000);
  }

  /** Force a refresh — also called when the board SSE fires TASK_UPDATED. */
  refresh(): void {
    void (async () => {
      try {
        const response = await this.client.getRunningAgents();
        if (this.disposed) return;
        this.agents = response.agents;
        this._onDidChangeTreeData.fire(undefined);
      } catch {
        // Best-effort — tree stays stale; background poll will retry.
      }
    })();
  }

  getTreeItem(element: RunningAgentItem): vscode.TreeItem {
    if (element.kind === "header") {
      const item = new vscode.TreeItem(
        element.label,
        vscode.TreeItemCollapsibleState.None,
      );
      item.contextValue = "runningAgentsHeader";
      return item;
    }

    const { agent } = element;
    const role = agent.agent_role ?? "worker";
    const elapsed = fmtElapsed(agent.started_at);
    const tokens = `↑${fmtTokens(agent.input_tokens)} ↓${fmtTokens(agent.output_tokens)}`;

    const item = new vscode.TreeItem(
      agent.task_title,
      vscode.TreeItemCollapsibleState.None,
    );
    item.description = `${role} · ${elapsed} · ${tokens}`;
    item.tooltip = `Session: ${agent.session_id}\nBackend: ${agent.agent_backend}\nStatus: ${agent.session_status}`;
    item.contextValue = `runningAgent.${role}`;
    item.iconPath = new vscode.ThemeIcon(
      role === "reviewer" ? "eye" : "play",
    );
    item.command = {
      command: "kagan.attachToSession",
      title: "Attach to Agent",
      arguments: [agent.session_id, agent.task_title],
    };
    return item;
  }

  getChildren(element?: RunningAgentItem): RunningAgentItem[] {
    // Root level
    if (!element) {
      if (this.agents.length === 0) {
        return [{ kind: "header", label: "No agents running" }];
      }
      return this.agents.map((agent) => ({ kind: "agent", agent }));
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

function fmtElapsed(startedAt: string): string {
  const s = Math.floor((Date.now() - new Date(startedAt).getTime()) / 1000);
  if (s < 60) return `${s}s`;
  const m = Math.floor(s / 60);
  return m < 60 ? `${m}m` : `${Math.floor(m / 60)}h`;
}

function fmtTokens(n: number | null | undefined): string {
  if (!n) return "0";
  return n >= 1000 ? `${(n / 1000).toFixed(1)}k` : String(n);
}
