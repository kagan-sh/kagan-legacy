import * as vscode from "vscode";
import type { KaganClient } from "../api/client.js";

function formatDuration(seconds: number | null): string {
  if (seconds == null) return "--";
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`;
}

function formatPct(v: number): string {
  return `${(v * 100).toFixed(1)}%`;
}

export function registerAnalyticsCommands(
  context: vscode.ExtensionContext,
  client: KaganClient,
): void {
  context.subscriptions.push(
    vscode.commands.registerCommand("kagan.analytics.show", async () => {
      await withErrors("show analytics", async () => {
        const [stats, timeline] = await Promise.all([
          client.getBackendStats(),
          client.getSessionTimeline(30),
        ]);

        const lines: string[] = [];

        // Backend performance table
        lines.push("# Backend Performance\n");
        if (stats.length === 0) {
          lines.push("No backend data yet. Run some sessions to see metrics.\n");
        } else {
          lines.push("| Backend | Sessions | Success | Avg Duration | Retry |");
          lines.push("|---------|----------|---------|--------------|-------|");
          for (const s of stats) {
            lines.push(
              `| ${s.agent_backend} | ${s.count} | ${formatPct(s.success_rate)} | ${formatDuration(s.avg_duration_seconds)} | ${formatPct(s.retry_rate)} |`,
            );
          }
          lines.push("");
        }

        // Session activity summary
        lines.push("# Session Activity (30 days)\n");
        if (timeline.length === 0) {
          lines.push("No session activity in this period.\n");
        } else {
          const total = timeline.reduce((sum, d) => sum + d.total, 0);
          const completed = timeline.reduce((sum, d) => sum + d.completed, 0);
          const failed = timeline.reduce((sum, d) => sum + d.failed, 0);
          const daysActive = timeline.filter((d) => d.total > 0).length;

          lines.push(`- **Total sessions:** ${total}`);
          lines.push(`- **Completed:** ${completed}`);
          lines.push(`- **Failed:** ${failed}`);
          lines.push(`- **Active days:** ${daysActive} / ${timeline.length}`);
          if (total > 0) {
            lines.push(`- **Success rate:** ${formatPct(completed / total)}`);
          }
        }

        const content = lines.join("\n");
        const doc = await vscode.workspace.openTextDocument({
          language: "markdown",
          content,
        });
        await vscode.window.showTextDocument(doc, { preview: true });
      });
    }),

    vscode.commands.registerCommand("kagan.analytics.export", async () => {
      await withErrors("export analytics", async () => {
        const data = await client.getAnalyticsExport();
        const uri = await vscode.window.showSaveDialog({
          defaultUri: vscode.Uri.file("kagan-analytics.json"),
          filters: { JSON: ["json"] },
        });
        if (!uri) return;
        const content = new TextEncoder().encode(JSON.stringify(data, null, 2));
        await vscode.workspace.fs.writeFile(uri, content);
        vscode.window.showInformationMessage(`Analytics exported to ${uri.fsPath}`);
      });
    }),
  );
}

async function withErrors(action: string, run: () => Promise<void>): Promise<void> {
  try {
    await run();
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    vscode.window.showErrorMessage(`Failed to ${action}: ${message}`);
  }
}
