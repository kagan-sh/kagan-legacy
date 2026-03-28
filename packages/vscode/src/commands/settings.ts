import * as vscode from "vscode";
import type { KaganClient } from "../api/client.js";

const REVIEW_STRICTNESS_OPTIONS = [
  { label: "Strict", description: "All criteria must pass, detailed review", value: "strict" },
  { label: "Balanced", description: "Default review depth", value: "balanced" },
  { label: "Relaxed", description: "Lenient review, quick pass", value: "relaxed" },
];

const PLANNING_DEPTH_OPTIONS = [
  { label: "Always", description: "Plan before every task", value: "always" },
  { label: "Multi-task", description: "Plan only for larger work", value: "multi_task" },
  { label: "Never", description: "Skip explicit planning", value: "never" },
];

export function registerSettingsCommands(
  context: vscode.ExtensionContext,
  client: KaganClient,
): void {
  context.subscriptions.push(
    vscode.commands.registerCommand("kagan.settings.agentBackend", async () => {
      await withErrors("set agent backend", async () => {
        const chatAgents = await client.getChatAgents();
        const currentBackend = chatAgents.default;
        const backends = chatAgents.backends;

        if (backends.length === 0) {
          vscode.window.showWarningMessage("No agent backends are available on this server.");
          return;
        }

        const picked = await vscode.window.showQuickPick(
          backends.map((backend) => ({
            label: backend.name,
            description: backend.name === currentBackend
              ? backend.available
                ? "Current"
                : "Current, unavailable"
              : backend.available
                ? undefined
                : "Unavailable",
          })),
          { placeHolder: `Select default agent backend (current: ${currentBackend})` },
        );
        if (!picked) return;

        await client.updateSettings({ default_agent_backend: picked.label });
        vscode.window.showInformationMessage(`Default agent backend set to ${picked.label}`);
      });
    }),

    vscode.commands.registerCommand("kagan.settings.reviewStrictness", async () => {
      await withErrors("set review strictness", async () => {
        const current = await client.getSettings();
        const currentStrictness = current.review_strictness ?? "balanced";

        const picked = await vscode.window.showQuickPick(
          REVIEW_STRICTNESS_OPTIONS.map((opt) => ({
            ...opt,
            description:
              opt.value === currentStrictness
                ? `${opt.description} (Current)`
                : opt.description,
          })),
          { placeHolder: `Select review strictness (current: ${currentStrictness})` },
        );
        if (!picked) return;

        await client.updateSettings({ review_strictness: picked.value });
        vscode.window.showInformationMessage(`Review strictness set to ${picked.value}`);
      });
    }),

    vscode.commands.registerCommand("kagan.settings.planningDepth", async () => {
      await withErrors("set planning depth", async () => {
        const current = await client.getSettings();
        const currentDepth = current.planning_depth ?? "always";

        const picked = await vscode.window.showQuickPick(
          PLANNING_DEPTH_OPTIONS.map((opt) => ({
            ...opt,
            description: opt.value === currentDepth ? `${opt.description} (Current)` : opt.description,
          })),
          { placeHolder: `Select planning depth (current: ${currentDepth})` },
        );
        if (!picked) return;

        await client.updateSettings({ planning_depth: picked.value });
        vscode.window.showInformationMessage(`Planning depth set to ${picked.value}`);
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
