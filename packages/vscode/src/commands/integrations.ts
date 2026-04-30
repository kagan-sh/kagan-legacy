import * as vscode from "vscode";
import type { KaganClient } from "../api/client.js";
import type { BoardTreeProvider } from "../providers/board.tree.js";
import { withErrors } from "./common.js";

export function registerIntegrationCommands(
  context: vscode.ExtensionContext,
  client: KaganClient,
  boardProvider: BoardTreeProvider,
): void {
  context.subscriptions.push(
    vscode.commands.registerCommand("kagan.github.import", async () => {
      await withErrors("import from GitHub", async () => {
        // Step 1: detect repo
        let repoSlug = "";
        try {
          const detected = await client.detectGithubRepo();
          if (detected.repo_slug) repoSlug = detected.repo_slug;
        } catch {
          // non-blocking
        }

        // Step 1b: allow user to override
        const repoInput = await vscode.window.showInputBox({
          prompt: "GitHub repository (owner/repo)",
          value: repoSlug,
          placeHolder: "e.g. octocat/hello-world",
          validateInput: (v) => (v.trim() ? undefined : "Repository is required"),
        });
        if (!repoInput) return;
        repoSlug = repoInput.trim();

        // Step 2: state filter
        const statePick = await vscode.window.showQuickPick(
          [
            { label: "Open", value: "open" },
            { label: "Closed", value: "closed" },
            { label: "All", value: "all" },
          ],
          { placeHolder: "Issue state filter" },
        );
        if (!statePick) return;

        // Step 3: labels (optional CSV)
        const labelsInput = await vscode.window.showInputBox({
          prompt: "Labels (optional, comma-separated)",
          placeHolder: "e.g. bug, enhancement",
        });
        if (labelsInput === undefined) return;

        // Step 4: preview
        let previewResult: Awaited<ReturnType<KaganClient["previewGithubIssues"]>>;
        await vscode.window.withProgress(
          { location: vscode.ProgressLocation.Notification, title: "Fetching GitHub issues…" },
          async () => {
            previewResult = await client.previewGithubIssues({
              repo_slug: repoSlug,
              state: statePick.value,
              labels: labelsInput.trim() || undefined,
              limit: 100,
            });
          },
        );

        // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
        const issues = previewResult!.issues;
        if (issues.length === 0) {
          void vscode.window.showInformationMessage("No issues match the filters.");
          return;
        }

        // Step 5: multi-select
        const picks = await vscode.window.showQuickPick(
          issues.map((issue) => ({
            label: `#${issue.number} ${issue.title}`,
            description: issue.already_synced ? "(already synced)" : issue.state,
            picked: !issue.already_synced,
            issueNumber: issue.number,
          })),
          {
            canPickMany: true,
            placeHolder: `Select issues to import (${issues.length} found)`,
          },
        );
        if (!picks || picks.length === 0) return;

        // Step 6: sync
        const config: Record<string, unknown> = {
          repo_slug: repoSlug,
          state: statePick.value,
          issue_numbers: picks.map((p) => p.issueNumber),
        };
        if (labelsInput.trim()) {
          config.labels = labelsInput.trim().split(",").map((l) => l.trim());
        }

        let syncResult: Awaited<ReturnType<KaganClient["syncGithubIssues"]>>;
        await vscode.window.withProgress(
          { location: vscode.ProgressLocation.Notification, title: "Importing issues…" },
          async () => {
            syncResult = await client.syncGithubIssues(config);
          },
        );

        // eslint-disable-next-line @typescript-eslint/no-non-null-assertion
        const r = syncResult!;
        const parts: string[] = [];
        if (r.created > 0) parts.push(`${r.created} created`);
        if (r.updated > 0) parts.push(`${r.updated} updated`);
        if (r.skipped > 0) parts.push(`${r.skipped} skipped`);
        if (r.errors.length > 0) parts.push(`${r.errors.length} errors`);

        const summary = parts.length > 0 ? parts.join(", ") : "Import complete";
        void vscode.window.showInformationMessage(`GitHub import: ${summary}`);
        boardProvider.refresh();
      });
    }),
  );
}
