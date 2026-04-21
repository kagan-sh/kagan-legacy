// DoctorStatusProvider — calls GET /api/doctor once on activation and
// reflects the result in the status bar. On FAIL, surfaces a Quick Fix
// notification with "Open TUI" and "Open Web" actions.
//
// Runs exactly once; does not poll. Server-unreachable errors are caught
// and mapped to the "offline" state — no unhandled exceptions.

import * as vscode from "vscode";
import type { KaganClient } from "../api/client.js";
import type { StatusBar } from "../status/bar.js";

export class DoctorStatusProvider {
  constructor(
    private readonly client: KaganClient,
    private readonly statusBar: StatusBar,
  ) {}

  async runPreflight(): Promise<void> {
    let report: Awaited<ReturnType<KaganClient["getDoctor"]>>;
    try {
      report = await this.client.getDoctor();
    } catch {
      // Server unreachable or returned an unexpected error — stay offline.
      return;
    }

    const failCount = report.fail_count;
    const warnCount = report.warn_count;

    if (failCount > 0) {
      this.statusBar.showSetupNeeded(failCount);
      void this.showFailNotification();
      return;
    }

    if (warnCount > 0) {
      this.statusBar.showDegraded(warnCount);
      return;
    }

    this.statusBar.showReady();
  }

  private async showFailNotification(): Promise<void> {
    const choice = await vscode.window.showWarningMessage(
      "Kagan: setup needed — one or more required checks failed.",
      "Open TUI",
      "Open Web",
    );

    if (choice === "Open TUI") {
      const terminal = vscode.window.createTerminal({ name: "Kagan TUI" });
      terminal.show();
      terminal.sendText("kagan tui", true);
      return;
    }

    if (choice === "Open Web") {
      const config = vscode.workspace.getConfiguration("kagan");
      const serverUrl = config.get<string>("serverUrl", "localhost:8765");
      const protocol = config.get<string>("protocol", "http");
      await vscode.env.openExternal(vscode.Uri.parse(`${protocol}://${serverUrl}`));
    }
  }
}
