import * as path from "node:path";
import * as vscode from "vscode";
import type { KaganClient } from "../api/client.js";
import type { WireTask } from "@kagan/shared-api-client";
import { buildEditorLink, normalizeLauncher } from "./tasks.terminal.helpers.js";

function createKaganTerminal(task: WireTask, cwd: string | null): vscode.Terminal {
  const terminal = vscode.window.createTerminal({
    name: `Kagan: ${task.title}`,
    cwd: cwd ?? undefined,
  });
  terminal.show();
  return terminal;
}

export class AgentTerminalProvider {
  constructor(private readonly client: KaganClient) {}

  async attachToTask(task: WireTask): Promise<void> {
    if (!task.active_session) {
      await vscode.window.showErrorMessage(`Task "${task.title}" has no active session.`);
      return;
    }

    const settings = await this.client.getSettings();
    const launcher = normalizeLauncher(
      task.active_session.launcher ?? task.launcher ?? settings.attached_launcher ?? "vscode",
    );

    const worktree = await this.client.getTaskWorktree(task.id);
    const worktreePath = worktree.worktree?.path ?? null;

    if (launcher === "tmux") {
      const sessionName = `kagan-${task.active_session.id.replaceAll(":", "-")}`;
      createKaganTerminal(task, worktreePath).sendText(`tmux attach-session -t '${sessionName}'`, true);
      return;
    }

    if (launcher === "nvim") {
      createKaganTerminal(task, worktreePath).sendText("nvim .kagan/start_prompt.md", true);
      return;
    }

    if (launcher === "vscode" && worktreePath) {
      const promptUri = vscode.Uri.file(path.join(worktreePath, ".kagan", "start_prompt.md"));
      await vscode.window.showTextDocument(promptUri, { preview: false });
      createKaganTerminal(task, worktreePath);
      return;
    }

    if (!worktreePath) {
      await vscode.window.showWarningMessage(`Task "${task.title}" has no worktree yet.`);
      return;
    }

    const deepLink = buildEditorLink(launcher, worktreePath);
    await vscode.env.openExternal(vscode.Uri.parse(deepLink));
  }
}
