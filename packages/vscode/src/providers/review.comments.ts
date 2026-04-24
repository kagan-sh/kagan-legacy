import * as vscode from "vscode";
import type { ReviewVerdict, WireTask } from "../api/types.js";
import { buildReviewDocument } from "./review.document.js";

const REVIEW_SCHEME = "kagan-review";

export class ReviewDocumentProvider implements vscode.TextDocumentContentProvider {
  private readonly tasks = new Map<string, WireTask>();
  private readonly didChange = new vscode.EventEmitter<vscode.Uri>();
  readonly onDidChange = this.didChange.event;

  setTask(task: WireTask): void {
    this.tasks.set(task.id, task);
    this.didChange.fire(reviewUri(task.id));
  }

  async provideTextDocumentContent(uri: vscode.Uri): Promise<string> {
    return buildReviewDocument(this.tasks.get(taskIdFromUri(uri)) ?? null).text;
  }

  dispose(): void {
    this.didChange.dispose();
  }
}

export class ReviewCommentProvider implements vscode.Disposable {
  private readonly controller: vscode.CommentController;
  private threads: vscode.CommentThread[] = [];

  constructor(private readonly documents: ReviewDocumentProvider) {
    this.controller = vscode.comments.createCommentController("kagan-review", "Kagan Review");
  }

  async showTaskReview(task: WireTask): Promise<void> {
    this.documents.setTask(task);
    const uri = buildReviewUri(task);
    await vscode.window.showTextDocument(uri, { preview: false });
    this.showVerdicts(task, uri);
  }

  clear(): void {
    for (const thread of this.threads) {
      thread.dispose();
    }
    this.threads = [];
  }

  dispose(): void {
    this.clear();
    this.controller.dispose();
  }

  private showVerdicts(task: WireTask, uri: vscode.Uri): void {
    this.clear();

    const { criterionLabels, criterionLines } = buildReviewDocument(task);

    for (const verdict of task.review_verdicts) {
      const line = criterionLines.get(verdict.criterion_id);
      if (line === undefined) continue;
      const range = new vscode.Range(line, 0, line, 0);
      const comment: vscode.Comment = {
        body: buildCommentBody(verdict),
        author: { name: "Kagan Reviewer" },
        mode: vscode.CommentMode.Preview,
      };

      const thread = this.controller.createCommentThread(uri, range, [comment]);
      thread.label = `Criterion ${criterionLabels.get(verdict.criterion_id) ?? "?"}`;
      thread.state =
        verdict.verdict === "PASS"
          ? vscode.CommentThreadState.Resolved
          : vscode.CommentThreadState.Unresolved;
      this.threads.push(thread);
    }
  }
}

function buildReviewUri(task: WireTask): vscode.Uri {
  return reviewUri(task.id);
}

function reviewUri(taskId: string): vscode.Uri {
  return vscode.Uri.from({
    scheme: REVIEW_SCHEME,
    path: `/${taskId}.md`,
  });
}

function buildCommentBody(verdict: ReviewVerdict): vscode.MarkdownString {
  const icon = verdict.verdict === "PASS" ? "$(pass)" : "$(error)";
  return new vscode.MarkdownString(`${icon} ${verdict.reason}`);
}

function taskIdFromUri(uri: vscode.Uri): string {
  return uri.path.replace(/^\/|\.md$/g, "");
}
