/**
 * MentionLinkProvider — DocumentLinkProvider for plaintext and markdown.
 *
 * Resolves:
 *   kagan#<8+ hex chars>  → command:kagan.task.open?<encoded-id>
 *   #<digits>              → https://github.com/<slug>/issues/<n>
 *
 * The GitHub slug is fetched once from detectGithubRepo and cached per document.
 */
import * as vscode from "vscode";
import type { KaganClient } from "../api/client.js";

const KAGAN_MENTION_RE = /\bkagan#([0-9a-f]{8,})\b/g;
const GITHUB_MENTION_RE = /(?:^|[\s(])(#(\d+))(?=$|[\s),.])/gm;

export class MentionLinkProvider implements vscode.DocumentLinkProvider {
  private cachedSlug: string | null = null;
  private slugFetched = false;

  constructor(private readonly client: KaganClient) {}

  async provideDocumentLinks(
    document: vscode.TextDocument,
  ): Promise<vscode.DocumentLink[]> {
    const links: vscode.DocumentLink[] = [];
    const text = document.getText();

    // Resolve kagan#... links
    KAGAN_MENTION_RE.lastIndex = 0;
    let m: RegExpExecArray | null;
    while ((m = KAGAN_MENTION_RE.exec(text)) !== null) {
      const taskId = m[1];
      const start = document.positionAt(m.index);
      const end = document.positionAt(m.index + m[0].length);
      const range = new vscode.Range(start, end);
      const commandUri = vscode.Uri.parse(
        `command:kagan.task.open?${encodeURIComponent(JSON.stringify({ id: taskId }))}`,
      );
      const link = new vscode.DocumentLink(range, commandUri);
      link.tooltip = `Open kagan task ${m[0]}`;
      links.push(link);
    }

    // Resolve #N links (needs GitHub slug)
    const slug = await this.getSlug();
    if (slug) {
      GITHUB_MENTION_RE.lastIndex = 0;
      while ((m = GITHUB_MENTION_RE.exec(text)) !== null) {
        const fullMatch = m[1]; // `#N`
        const number = m[2];
        const matchStart = m.index + m[0].indexOf(fullMatch);
        const start = document.positionAt(matchStart);
        const end = document.positionAt(matchStart + fullMatch.length);
        const range = new vscode.Range(start, end);
        const uri = vscode.Uri.parse(`https://github.com/${slug}/issues/${number}`);
        const link = new vscode.DocumentLink(range, uri);
        link.tooltip = `Open GitHub issue #${number}`;
        links.push(link);
      }
    }

    return links;
  }

  private async getSlug(): Promise<string | null> {
    if (this.slugFetched) return this.cachedSlug;
    try {
      const result = await this.client.detectGithubRepo();
      this.cachedSlug = result.repo_slug ?? null;
    } catch {
      this.cachedSlug = null;
    }
    this.slugFetched = true;
    return this.cachedSlug;
  }

  /** Invalidate the slug cache (e.g. when project changes). */
  invalidateCache(): void {
    this.slugFetched = false;
    this.cachedSlug = null;
  }
}
