import * as vscode from "vscode";
import type { ReviewVerdict, WireTask } from "../api/types.js";

const REVIEW_SCHEME = "kagan-review";

export class ReviewDocumentProvider implements vscode.TextDocumentContentProvider {
  async provideTextDocumentContent(uri: vscode.Uri): Promise<string> {
    const query = new URLSearchParams(uri.query);
    const encoded = query.get("payload");
    if (!encoded) {
      return "";
    }

    const task = JSON.parse(decodeURIComponent(encoded)) as WireTask;
    return buildReviewDocument(task);
  }
}

export class ReviewCommentProvider implements vscode.Disposable {
  private readonly controller: vscode.CommentController;
  private threads: vscode.CommentThread[] = [];

  constructor() {
    this.controller = vscode.comments.createCommentController("kagan-review", "Kagan Review");
  }

  async showTaskReview(task: WireTask): Promise<void> {
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

    for (const verdict of task.review_verdicts) {
      const line = criterionLine(verdict.criterion_index);
      const range = new vscode.Range(line, 0, line, 0);
      const comment: vscode.Comment = {
        body: buildCommentBody(verdict),
        author: { name: "Kagan Reviewer" },
        mode: vscode.CommentMode.Preview,
      };

      const thread = this.controller.createCommentThread(uri, range, [comment]);
      thread.label = `Criterion ${verdict.criterion_index + 1}`;
      thread.state =
        verdict.verdict === "PASS"
          ? vscode.CommentThreadState.Resolved
          : vscode.CommentThreadState.Unresolved;
      this.threads.push(thread);
    }
  }
}

function buildReviewUri(task: WireTask): vscode.Uri {
  return vscode.Uri.from({
    scheme: REVIEW_SCHEME,
    path: `/${task.id}.md`,
    query: new URLSearchParams({
      payload: encodeURIComponent(JSON.stringify(task)),
    }).toString(),
  });
}

function buildReviewDocument(task: WireTask): string {
  const lines = [
    `# ${task.title}`,
    "",
    `Status: ${task.status}`,
    `Priority: ${task.priority}`,
    `Approved: ${task.review_approved ? "yes" : "no"}`,
    "",
    "## Acceptance Criteria",
    "",
  ];

  const criteria = task.acceptance_criteria.length > 0 ? task.acceptance_criteria : ["No acceptance criteria"];
  for (const [index, criterion] of criteria.entries()) {
    const verdict = task.review_verdicts.find((item) => item.criterion_index === index);
    const marker = verdict?.verdict === "PASS" ? "[PASS]" : verdict?.verdict === "FAIL" ? "[FAIL]" : "[ ]";
    lines.push(`${index + 1}. ${marker} ${criterion}`);
  }

  if (task.review_verdicts.length > 0) {
    lines.push("", "## Verdict Summary", "");
    for (const verdict of task.review_verdicts) {
      lines.push(`${verdict.criterion_index + 1}. ${verdict.verdict}: ${verdict.reason}`);
    }
  }

  return lines.join("\n");
}

function buildCommentBody(verdict: ReviewVerdict): vscode.MarkdownString {
  const icon = verdict.verdict === "PASS" ? "$(pass)" : "$(error)";
  return new vscode.MarkdownString(`${icon} ${verdict.reason}`);
}

/** Header lines before criteria: title, blank, status, priority, approved, blank, heading, blank */
const CRITERIA_START_LINE = 8;

function criterionLine(index: number): number {
  return CRITERIA_START_LINE + index;
}
