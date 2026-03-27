import * as vscode from "vscode";
import type { KaganClient } from "../api/client.js";
import type { DiffFile, WireTask } from "../api/types.js";
import { extractPatchForFile } from "./tasks.scm.helpers.js";

const DIFF_SCHEME = "kagan-diff";

const STATUS_DECORATIONS: Record<string, { icon: string; tooltip: string }> = {
  added: { icon: "diff-added", tooltip: "Added" },
  modified: { icon: "diff-modified", tooltip: "Modified" },
  deleted: { icon: "diff-removed", tooltip: "Deleted" },
  renamed: { icon: "diff-renamed", tooltip: "Renamed" },
};

export class TaskScmProvider implements vscode.Disposable {
  private scm: vscode.SourceControl | null = null;
  private group: vscode.SourceControlResourceGroup | null = null;

  constructor(private readonly client: KaganClient) {}

  async showTaskDiff(task: WireTask): Promise<void> {
    const [stats, files] = await Promise.all([
      this.client.getDiffStats(task.id),
      this.client.getDiffFiles(task.id),
    ]);

    this.clear();

    this.scm = vscode.scm.createSourceControl(`kagan-${task.id}`, `Kagan: ${task.title}`);
    this.scm.count = stats.files_changed;
    this.scm.inputBox.visible = false;
    this.group = this.scm.createResourceGroup("changes", "Changes");
    this.group.hideWhenEmpty = true;
    this.group.resourceStates = files.map((file) => fileToResourceState(task.id, file));

    await vscode.commands.executeCommand("workbench.view.scm");

    const targetUri =
      files.length > 0
        ? buildDiffUri(task.id, files[0].path, files[0].path)
        : buildDiffUri(task.id, task.title);
    await vscode.window.showTextDocument(targetUri, { preview: false });
  }

  clear(): void {
    this.group?.dispose();
    this.group = null;
    this.scm?.dispose();
    this.scm = null;
  }

  dispose(): void {
    this.clear();
  }
}

export class KaganDiffContentProvider implements vscode.TextDocumentContentProvider {
  constructor(private readonly client: KaganClient) {}

  async provideTextDocumentContent(uri: vscode.Uri): Promise<string> {
    const query = new URLSearchParams(uri.query);
    const taskId = query.get("task");
    const filePath = query.get("file");

    if (!taskId) {
      return "";
    }

    try {
      const diff = await this.client.getDiffRaw(taskId);
      if (!filePath) {
        return diff;
      }
      return extractPatchForFile(diff, filePath);
    } catch {
      return `// Failed to load diff for ${filePath ?? taskId}`;
    }
  }
}

function fileToResourceState(taskId: string, file: DiffFile): vscode.SourceControlResourceState {
  const resourceUri = buildDiffUri(taskId, file.path, file.path);
  return {
    resourceUri,
    decorations: decorationForStatus(file.status, file),
    command: {
      title: "Open Patch",
      command: "vscode.open",
      arguments: [resourceUri, { preview: false }],
    },
  };
}

function decorationForStatus(
  status: string,
  file: DiffFile,
): vscode.SourceControlResourceDecorations {
  const entry = STATUS_DECORATIONS[status] ?? STATUS_DECORATIONS["modified"];
  return {
    iconPath: new vscode.ThemeIcon(entry.icon),
    tooltip: `${entry.tooltip} • +${file.insertions} -${file.deletions}`,
  };
}

function buildDiffUri(taskId: string, label: string, filePath?: string): vscode.Uri {
  const query = new URLSearchParams({ task: taskId });
  if (filePath) {
    query.set("file", filePath);
  }
  return vscode.Uri.from({
    scheme: DIFF_SCHEME,
    path: `/${label}.diff`,
    query: query.toString(),
  });
}
