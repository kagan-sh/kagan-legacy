import * as path from "node:path";
import * as vscode from "vscode";
import type { KaganClient } from "../api/client.js";
import type { WireTask } from "../api/types.js";
import { buildEditorLink, normalizeLauncher } from "./tasks.terminal.helpers.js";

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
      const terminal = vscode.window.createTerminal({
        name: `Kagan: ${task.title}`,
        cwd: worktreePath ?? undefined,
      });
      terminal.show();
      terminal.sendText(`tmux attach-session -t ${sessionName}`, true);
      return;
    }

    if (launcher === "nvim") {
      const terminal = vscode.window.createTerminal({
        name: `Kagan: ${task.title}`,
        cwd: worktreePath ?? undefined,
      });
      terminal.show();
      terminal.sendText("nvim .kagan/start_prompt.md", true);
      return;
    }

    if (launcher === "vscode" && worktreePath) {
      const promptUri = vscode.Uri.file(path.join(worktreePath, ".kagan", "start_prompt.md"));
      await vscode.window.showTextDocument(promptUri, { preview: false });

      const terminal = vscode.window.createTerminal({
        name: `Kagan: ${task.title}`,
        cwd: worktreePath,
      });
      terminal.show();
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
