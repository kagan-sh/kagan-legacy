/**
 * MentionCompletionProvider — CompletionItemProvider for `#` triggers.
 *
 * Registered for plaintext and markdown documents. On invocation, parses
 * the substring after `#` at the cursor and calls KaganClient.searchMentions.
 * Returns CompletionItem[] with source-tagged details and the correct insert string.
 */
import * as vscode from "vscode";
import type { KaganClient } from "../api/client.js";

export class MentionCompletionProvider implements vscode.CompletionItemProvider {
  constructor(private readonly client: KaganClient) {}

  async provideCompletionItems(
    document: vscode.TextDocument,
    position: vscode.Position,
    _token: vscode.CancellationToken,
  ): Promise<vscode.CompletionItem[] | null> {
    const lineText = document.lineAt(position).text;
    const linePrefix = lineText.slice(0, position.character);

    // Find `#` at word-start in the line prefix
    const hashMatch = /(?:^|[\s\t])(#(\S*))$/.exec(linePrefix);
    if (!hashMatch) return null;

    const query = hashMatch[2] ?? "";

    // Resolve active project id
    let projectId: string | null = null;
    try {
      const projects = await this.client.getProjects();
      const active = projects.find((p) => p.active) ?? projects[0];
      projectId = active?.id ?? null;
    } catch {
      return null;
    }

    if (!projectId) return null;

    let mentions: Awaited<ReturnType<KaganClient["searchMentions"]>>;
    try {
      mentions = await this.client.searchMentions({ projectId, q: query, limit: 15 });
    } catch {
      return null;
    }

    // Compute the range that will be replaced (from `#` to cursor)
    const hashStart = position.character - hashMatch[1].length;
    const replaceRange = new vscode.Range(
      position.line,
      hashStart,
      position.line,
      position.character,
    );

    return mentions.map((mention) => {
      const item = new vscode.CompletionItem(
        mention.id,
        vscode.CompletionItemKind.Reference,
      );
      const sourceLabel = mention.source === "kagan" ? "◆ kagan" : "◇ github";
      item.detail = `${sourceLabel} — ${mention.title.slice(0, 60)}`;
      item.documentation = new vscode.MarkdownString(
        mention.state ? `**${mention.title}** (${mention.state})` : `**${mention.title}**`,
      );
      item.insertText = mention.id;
      item.range = replaceRange;
      item.sortText = mention.source === "kagan" ? `a_${mention.id}` : `b_${mention.id}`;
      return item;
    });
  }
}
