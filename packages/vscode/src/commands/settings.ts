import * as vscode from "vscode";
import type { KaganClient } from "../api/client.js";
import type { AgentBackendResponse } from "@kagan/shared-api-client";
import { withErrors } from "./common.js";

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

export function sortBackends(backends: AgentBackendResponse[]): AgentBackendResponse[] {
  return [...backends].sort((a, b) => {
    if (a.reference !== b.reference) return a.reference ? -1 : 1;
    if (a.available !== b.available) return a.available ? -1 : 1;
    return a.name.localeCompare(b.name);
  });
}

export function describeBackendStatus(
  backend: AgentBackendResponse,
  currentBackend: string,
): string | undefined {
  const parts: string[] = [];

  if (backend.name === currentBackend) {
    parts.push("Current");
  }
  if (backend.reference) {
    parts.push("Reference");
  }
  if (!backend.available) {
    parts.push("Unavailable");
  }

  return parts.length > 0 ? parts.join(" · ") : undefined;
}

async function pickSetting(
  client: KaganClient,
  key: string,
  options: { label: string; description: string; value: string }[],
  displayName: string,
): Promise<void> {
  const current = await client.getSettings();
  const currentValue = current[key] ?? options[0].value;

  const picked = await vscode.window.showQuickPick(
    options.map((opt) => ({
      ...opt,
      description: opt.value === currentValue ? `${opt.description} (Current)` : opt.description,
    })),
    { placeHolder: `Select ${displayName} (current: ${currentValue})` },
  );
  if (!picked) return;

  await client.updateSettings({ [key]: picked.value });
  vscode.window.showInformationMessage(`${displayName} set to ${picked.value}`);
}

export function registerSettingsCommands(
  context: vscode.ExtensionContext,
  client: KaganClient,
): void {
  context.subscriptions.push(
    vscode.commands.registerCommand("kagan.settings.agentBackend", async () => {
      await withErrors("set agent backend", async () => {
        const chatAgents = await client.getChatAgents();
        const currentBackend = chatAgents.default;
        const backends = sortBackends(chatAgents.backends);

        if (backends.length === 0) {
          vscode.window.showWarningMessage("No agent backends are available on this server.");
          return;
        }

        const picked = await vscode.window.showQuickPick(
          backends.map((backend) => ({
            label: backend.name,
            description: describeBackendStatus(backend, currentBackend),
          })),
          { placeHolder: `Select default agent backend (reference backends first, current: ${currentBackend})` },
        );
        if (!picked) return;

        await client.updateSettings({ default_agent_backend: picked.label });
        vscode.window.showInformationMessage(`Default agent backend set to ${picked.label}`);
      });
    }),

    vscode.commands.registerCommand("kagan.settings.reviewStrictness", async () => {
      await withErrors("set review strictness", () =>
        pickSetting(client, "review_strictness", REVIEW_STRICTNESS_OPTIONS, "review strictness"),
      );
    }),

    vscode.commands.registerCommand("kagan.settings.planningDepth", async () => {
      await withErrors("set planning depth", () =>
        pickSetting(client, "planning_depth", PLANNING_DEPTH_OPTIONS, "planning depth"),
      );
    }),
  );
}
