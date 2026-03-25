// Status bar item for Kagan connection state and task counts.
// "Readability counts." — one class, four states, no ambiguity.

import * as vscode from "vscode";

export class StatusBar implements vscode.Disposable {
  private readonly item: vscode.StatusBarItem;

  constructor() {
    this.item = vscode.window.createStatusBarItem(vscode.StatusBarAlignment.Left, 50);
  }

  showConnecting(): void {
    this.item.text = "$(sync~spin) Kagan: connecting...";
    this.item.tooltip = undefined;
    this.item.command = undefined;
    this.item.show();
  }

  showConnected(taskCounts: Record<string, number>): void {
    const total = Object.values(taskCounts).reduce((sum, n) => sum + n, 0);
    this.item.text = `$(list-tree) Kagan: ${total} tasks`;

    const md = new vscode.MarkdownString();
    md.appendText(
      [
        `BACKLOG: ${taskCounts["BACKLOG"] ?? 0}`,
        `IN_PROGRESS: ${taskCounts["IN_PROGRESS"] ?? 0}`,
        `REVIEW: ${taskCounts["REVIEW"] ?? 0}`,
        `DONE: ${taskCounts["DONE"] ?? 0}`,
      ].join(" | "),
    );
    this.item.tooltip = md;
    this.item.command = "kagan.board.refresh";
    this.item.show();
  }

  showDisconnected(): void {
    this.item.text = "$(debug-disconnect) Kagan: offline";
    this.item.tooltip = "Click to reconnect";
    this.item.command = "kagan.connect";
    this.item.show();
  }

  showError(msg: string): void {
    this.item.text = "$(error) Kagan: error";
    this.item.tooltip = msg;
    this.item.command = "kagan.connect";
    this.item.show();
  }

  dispose(): void {
    this.item.dispose();
  }
}
