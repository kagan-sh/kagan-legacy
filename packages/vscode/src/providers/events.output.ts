// Agent event output mapped to VS Code's native OutputChannel.

import * as vscode from "vscode";
import type { KaganClient } from "../api/client.js";
import type { WireEvent, WireTask, SSEMessage, EventType } from "../api/types.js";

// ── Output Channel ──────────────────────────────────────────────────────────

export class AgentOutputProvider implements vscode.Disposable {
  activeTaskId: string | null = null;
  private readonly channel: vscode.OutputChannel;

  constructor(private readonly client: KaganClient) {
    this.channel = vscode.window.createOutputChannel("Kagan: Agent Output");
  }

  async showTask(task: WireTask): Promise<void> {
    this.activeTaskId = task.id;
    this.channel.clear();
    this.channel.appendLine(`── ${task.title} ──\n`);

    const events = await this.client.getTaskEvents(task.id, { limit: 50 });
    for (const event of events) {
      this.channel.appendLine(this.formatEvent(event));
    }

    this.channel.show(true);
  }

  onSSE(msg: SSEMessage): void {
    if (msg.type !== "SESSION_EVENT") return;
    if (msg.task_id !== this.activeTaskId) return;
    this.channel.appendLine(this.formatEvent(msg.event));
  }

  private formatEvent(event: WireEvent): string {
    const p = event.payload;
    const type = event.type as EventType;

    switch (type) {
      case "OUTPUT_CHUNK":
        return String(p.text ?? "");
      case "AGENT_STATUS":
        return `[STATUS] ${p.status}`;
      case "TOOL_CALL_START":
        return `[TOOL] ${p.tool_name}(${JSON.stringify(p.input ?? {}).slice(0, 100)})`;
      case "TOOL_CALL_UPDATE":
        return `[TOOL] ${p.tool_name} → ${p.status}`;
      case "AGENT_COMPLETED":
        return "[DONE] Agent completed";
      case "AGENT_FAILED":
        return `[FAIL] ${p.error ?? "Agent failed"}`;
      case "TASK_STATUS_CHANGED":
        return `[STATUS] ${p.old_status} → ${p.new_status}`;
      case "MERGE_COMPLETED":
        return "[MERGE] Merge completed";
      case "MERGE_FAILED":
        return `[MERGE] Merge failed: ${p.error}`;
      default:
        return `[${event.type}] ${JSON.stringify(p)}`;
    }
  }

  dispose(): void {
    this.channel.dispose();
  }
}
