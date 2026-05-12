// Agent event output mapped to VS Code's native OutputChannel.
//
// Stopgap renderer — the primary agent output surface is the Chat
// Participant (@kagan).  This channel serves as a diagnostic log.
//
// Live updates arrive via the per-task KaganEventSource frame stream
// (GET /api/tasks/{id}/sse) rather than the global SSE broadcast.

import * as vscode from "vscode";
import type { KaganClient } from "../api/client.js";
import type { KaganEventSource } from "../api/event-source.js";
import { renderEvent } from "@kagan/shared-api-client";
import type { WireEvent, WireTask } from "@kagan/shared-api-client";

// ── Output Channel ──────────────────────────────────────────────────────────

export class AgentOutputProvider implements vscode.Disposable {
  activeTaskId: string | null = null;
  private readonly channel: vscode.OutputChannel;
  private lastWasText = false;
  private taskEs: KaganEventSource | null = null;

  constructor(private readonly client: KaganClient) {
    this.channel = vscode.window.createOutputChannel("Kagan: Agent Log");
  }

  async showTask(task: WireTask): Promise<void> {
    // Close any existing per-task stream before opening a new one.
    this.taskEs?.close();
    this.taskEs = null;

    this.activeTaskId = task.id;
    this.lastWasText = false;
    this.channel.clear();
    this.channel.appendLine(`-- ${task.title} --\n`);

    const events = await this.client.getTaskEvents(task.id, { limit: 50 });
    for (const event of events) {
      this.renderEvent(event);
    }

    // Subscribe to live task frame events for ongoing updates.
    const es = this.client.subscribeTaskEvents(task.id);
    this.taskEs = es;

    es.onPatch((patch) => {
      // Task frame patches carry agent output in text appends.
      if (patch.op === "append" && typeof patch.value === "string") {
        this.channel.append(patch.value);
        this.lastWasText = true;
      }
    });

    es.onError((err) => {
      console.warn("[kagan] agent output frame stream error:", err.message);
    });

    this.channel.show(true);
  }

  private renderEvent(event: WireEvent): void {
    const rendered = renderEvent(event.type, event.payload ?? {}, event.id, event.session_id ?? "");
    if (!rendered) return;

    switch (rendered.kind) {
      case "text":
      case "thought":
        if (!rendered.body) return;
        this.channel.append(rendered.body);
        this.lastWasText = true;
        return;

      case "tool_start":
        this.breakAfterText();
        this.channel.appendLine(`  > ${rendered.title}`);
        this.lastWasText = false;
        return;

      case "tool_update":
        this.breakAfterText();
        this.channel.appendLine(`  > ${rendered.title} -> ${rendered.body || "running"}`);
        this.lastWasText = false;
        return;

      case "status_change":
        this.breakAfterText();
        this.channel.appendLine(`[${rendered.title}]`);
        this.lastWasText = false;
        return;

      case "note":
        this.breakAfterText();
        this.channel.appendLine(`[NOTE] ${rendered.title}`);
        this.lastWasText = false;
        return;

      case "error":
        this.breakAfterText();
        this.channel.appendLine(`[FAIL] ${rendered.body || rendered.title}`);
        this.lastWasText = false;
        return;

      case "plan":
        this.breakAfterText();
        this.channel.appendLine(`  * ${rendered.title}`);
        this.lastWasText = false;
        return;

      case "merge":
        this.breakAfterText();
        this.channel.appendLine(`[MERGE] ${rendered.title}${rendered.body ? `: ${rendered.body}` : ""}`);
        this.lastWasText = false;
        return;

      case "verdict":
        this.breakAfterText();
        this.channel.appendLine(`  [${rendered.title}] ${rendered.body}`);
        this.lastWasText = false;
        return;

      default:
        this.breakAfterText();
        this.channel.appendLine(`[${rendered.title}] ${rendered.body}`.trim());
        this.lastWasText = false;
    }
  }

  private breakAfterText(): void {
    if (this.lastWasText) {
      this.channel.appendLine("");
    }
  }

  dispose(): void {
    this.taskEs?.close();
    this.taskEs = null;
    this.channel.dispose();
  }
}
