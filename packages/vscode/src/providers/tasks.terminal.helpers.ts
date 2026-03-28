import type { LauncherBackend } from "../api/types.js";

const DEEP_LINK_SCHEMES: Record<Exclude<LauncherBackend, "tmux" | "nvim">, string> = {
  vscode: "vscode",
  cursor: "cursor",
  windsurf: "windsurf",
  kiro: "kiro",
  antigravity: "antigravity",
};

export function normalizeLauncher(value: string): LauncherBackend {
  const normalized = value.trim().toLowerCase();
  switch (normalized) {
    case "tmux":
    case "nvim":
    case "vscode":
    case "cursor":
    case "windsurf":
    case "kiro":
    case "antigravity":
      return normalized;
    default:
      return "vscode";
  }
}

export function buildEditorLink(
  launcher: Exclude<LauncherBackend, "tmux" | "nvim">,
  worktreePath: string,
): string {
  const normalizedPath = worktreePath.includes("\\")
    ? worktreePath.replace(/\\/g, "/")
    : worktreePath;
  const filePath = /^[A-Za-z]:\//.test(normalizedPath) ? `/${normalizedPath}` : normalizedPath;
  return `${DEEP_LINK_SCHEMES[launcher]}://file${encodeURI(filePath)}`;
}
