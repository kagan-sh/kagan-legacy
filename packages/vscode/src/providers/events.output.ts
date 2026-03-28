// Agent event output mapped to VS Code's native OutputChannel.
//
// Stopgap renderer — the primary agent output surface is the Chat
// Participant (@kagan).  This channel serves as a diagnostic log.

import * as vscode from "vscode";
import type { KaganClient } from "../api/client.js";
import { EVENT_TYPE, SSE_TYPE } from "../api/types.js";
import { extractToolTitle, extractToolStatus } from "../api/event-helpers.js";
import type { WireEvent, WireTask, SSEMessage } from "../api/types.js";

// ── Output Channel ──────────────────────────────────────────────────────────

export class AgentOutputProvider implements vscode.Disposable {
  activeTaskId: string | null = null;
  private readonly channel: vscode.OutputChannel;
  private lastWasText = false;

  constructor(private readonly client: KaganClient) {
    this.channel = vscode.window.createOutputChannel("Kagan: Agent Log");
  }

  async showTask(task: WireTask): Promise<void> {
    this.activeTaskId = task.id;
    this.lastWasText = false;
    this.channel.clear();
    this.channel.appendLine(`-- ${task.title} --\n`);

    const events = await this.client.getTaskEvents(task.id, { limit: 50 });
    for (const event of events) {
      this.renderEvent(event);
    }

    this.channel.show(true);
  }

  onSSE(msg: SSEMessage): void {
    if (msg.type !== SSE_TYPE.SESSION_EVENT) return;
    if (msg.task_id !== this.activeTaskId) return;
    this.renderEvent(msg.event);
  }

  private renderEvent(event: WireEvent): void {
    const p = event.payload ?? {};

    switch (event.type) {
      case EVENT_TYPE.OUTPUT_CHUNK: {
        const text = String(p.text ?? "");
        if (!text) return;
        this.channel.append(text);
        this.lastWasText = true;
        return;
      }

      case EVENT_TYPE.TOOL_CALL_START: {
        this.breakAfterText();
        this.channel.appendLine(`  > ${extractToolTitle(p)}`);
        this.lastWasText = false;
        return;
      }

      case EVENT_TYPE.TOOL_CALL_UPDATE: {
        const status = extractToolStatus(p, "done");
        if (status !== "completed" && status !== "done") {
          this.breakAfterText();
          this.channel.appendLine(`  > ${extractToolTitle(p)} -> ${status}`);
          this.lastWasText = false;
        }
        return;
      }

      case EVENT_TYPE.AGENT_STATUS:
        return;

      case EVENT_TYPE.TASK_STATUS_CHANGED: {
        this.breakAfterText();
        this.channel.appendLine(`[${p.from ?? "?"} -> ${p.to ?? "?"}]`);
        this.lastWasText = false;
        return;
      }

      case EVENT_TYPE.AGENT_COMPLETED: {
        this.breakAfterText();
        this.channel.appendLine("[DONE] Agent completed");
        this.lastWasText = false;
        return;
      }

      case EVENT_TYPE.AGENT_FAILED: {
        this.breakAfterText();
        this.channel.appendLine(`[FAIL] ${p.error ?? "Agent failed"}`);
        this.lastWasText = false;
        return;
      }

      case EVENT_TYPE.PLAN_UPDATE: {
        this.breakAfterText();
        this.channel.appendLine("  * Plan updated");
        this.lastWasText = false;
        return;
      }

      case EVENT_TYPE.MERGE_COMPLETED: {
        this.breakAfterText();
        this.channel.appendLine("[MERGE] Merge completed");
        this.lastWasText = false;
        return;
      }

      case EVENT_TYPE.MERGE_FAILED: {
        this.breakAfterText();
        this.channel.appendLine(`[MERGE] Merge failed: ${p.error ?? "unknown"}`);
        this.lastWasText = false;
        return;
      }

      case EVENT_TYPE.CRITERION_VERDICT: {
        this.breakAfterText();
        const mark = String(p.verdict ?? "") === "PASS" ? "PASS" : "FAIL";
        this.channel.appendLine(`  [${mark}] ${p.reason ?? ""}`);
        this.lastWasText = false;
        return;
      }

      case EVENT_TYPE.AUTO_REVIEW_STARTED: {
        this.breakAfterText();
        this.channel.appendLine("  * Auto-review started");
        this.lastWasText = false;
        return;
      }

      default: {
        this.breakAfterText();
        this.channel.appendLine(`[${event.type}] ${JSON.stringify(p)}`);
        this.lastWasText = false;
      }
    }
  }

  private breakAfterText(): void {
    if (this.lastWasText) {
      this.channel.appendLine("");
    }
  }

  dispose(): void {
    this.channel.dispose();
  }
}
