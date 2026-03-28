import * as vscode from "vscode";
import type { KaganClient } from "../api/client.js";

const AGENT_BACKENDS = [
  "claude-code",
  "codex",
  "aider",
  "goose",
  "cline",
  "roo-code",
  "amp",
  "gemini-cli",
  "kilo-code",
  "copilot-agent",
  "junie",
  "trae-agent",
  "augment-agent",
  "cursor-agent",
];

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
        const current = await client.getSettings();
        const currentBackend = current.default_agent_backend ?? "claude-code";

        const picked = await vscode.window.showQuickPick(
          AGENT_BACKENDS.map((backend) => ({
            label: backend,
            description: backend === currentBackend ? "Current" : undefined,
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
