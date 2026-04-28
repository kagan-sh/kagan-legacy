import * as vscode from "vscode";
import type { KaganClient } from "../api/client.js";
import { formatDuration, formatPercentage } from "../lib/format.js";
import { withErrors } from "./common.js";

export function registerAnalyticsCommands(
  context: vscode.ExtensionContext,
  client: KaganClient,
): void {
  context.subscriptions.push(
    vscode.commands.registerCommand("kagan.analytics.show", async () => {
      await withErrors("show analytics summary", async () => {
        const range = await pickAnalyticsRange();
        if (!range) return;

        const [stats, timeline] = await Promise.all([
          client.getBackendStats({ days: range.days }),
          client.getSessionTimeline({ days: range.days }),
        ]);

        const lines: string[] = [];

        // Backend performance table
        lines.push(`# Analytics Summary (${range.label})\n`);
        lines.push("## Backend Performance\n");
        if (stats.length === 0) {
          lines.push("No backend data yet. Run some sessions to see metrics.\n");
        } else {
          lines.push("| Backend | Sessions | Success | Avg Duration | Retry |");
          lines.push("|---------|----------|---------|--------------|-------|");
          for (const s of stats) {
            lines.push(
              `| ${s.agent_backend} | ${s.count} | ${formatPercentage(s.success_rate)} | ${formatDuration(s.avg_duration_seconds)} | ${formatPercentage(s.retry_rate)} |`,
            );
          }
          lines.push("");
        }

        // Session activity summary
        lines.push(`## Session Activity (${range.label})\n`);
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
            lines.push(`- **Success rate:** ${formatPercentage(completed / total)}`);
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

async function pickAnalyticsRange(): Promise<{ label: string; days: number } | undefined> {
  const picked = await vscode.window.showQuickPick(
    [
      { label: "Last 30 days", days: 30 },
      { label: "Last 7 days", days: 7 },
      { label: "Last 90 days", days: 90 },
    ],
    { placeHolder: "Select analytics summary range" },
  );
  return picked;
}
