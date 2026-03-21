/** Supported launcher backends (matches LAUNCHER_OPTIONS in constants.ts) */
export type LauncherBackend =
  | 'tmux'
  | 'nvim'
  | 'vscode'
  | 'cursor'
  | 'windsurf'
  | 'kiro'
  | 'antigravity';

/** Result of building an editor link */
export interface EditorLinkResult {
  /** The URI or protocol link to open. null if this launcher doesn't support deep links. */
  uri: string | null;
  /** Human-readable label for the button */
  label: string;
  /** Whether this launcher supports URI protocol deep links from a browser */
  supportsDeepLink: boolean;
  /** Fallback message when deep links aren't supported */
  fallbackMessage: string | null;
}

type DeepLinkScheme = Exclude<LauncherBackend, 'tmux' | 'nvim'>;

const DEEP_LINK_SCHEMES: Record<DeepLinkScheme, string> = {
  vscode: 'vscode',
  cursor: 'cursor',
  windsurf: 'windsurf',
  kiro: 'kiro',
  antigravity: 'antigravity',
};

function normalizePathForUri(path: string): string {
  let normalized = path;

  if (normalized.includes('\\')) {
    normalized = normalized.replace(/\\/g, '/');
  }

  if (/^[A-Za-z]:\//.test(normalized)) {
    normalized = `/${normalized}`;
  }

  return normalized;
}

function buildDeepLinkUri(scheme: DeepLinkScheme, worktreePath: string): string {
  const normalizedPath = normalizePathForUri(worktreePath);
  const encodedPath = encodeURI(normalizedPath);
  return `${DEEP_LINK_SCHEMES[scheme]}://file${encodedPath}`;
}

/**
 * Build an editor deep link URI for the given launcher and worktree path.
 *
 * Supported URI schemes:
 * - vscode: vscode://file/{path}
 * - cursor: cursor://file/{path}
 * - windsurf: windsurf://file/{path}
 * - kiro: kiro://file/{path}
 * - antigravity: antigravity://file/{path}
 * - tmux: NO deep link (terminal app, needs web terminal or manual attach)
 * - nvim: NO deep link (terminal app, needs web terminal or manual attach)
 */
export function buildEditorLink(launcher: LauncherBackend, worktreePath: string): EditorLinkResult {
  if (launcher === 'tmux') {
    return {
      uri: null,
      label: `Open in ${launcherDisplayName(launcher)}`,
      supportsDeepLink: false,
      fallbackMessage:
        'tmux sessions run on the server. Attach via terminal: tmux attach-session -t kagan-{sessionId}',
    };
  }

  if (launcher === 'nvim') {
    return {
      uri: null,
      label: `Open in ${launcherDisplayName(launcher)}`,
      supportsDeepLink: false,
      fallbackMessage: `Neovim sessions run on the server. Open in terminal: nvim ${worktreePath}`,
    };
  }

  return {
    uri: buildDeepLinkUri(launcher, worktreePath),
    label: `Open in ${launcherDisplayName(launcher)}`,
    supportsDeepLink: true,
    fallbackMessage: null,
  };
}

/**
 * Try to open the editor via deep link.
 * Returns true if a deep link was attempted (doesn't guarantee the app opened).
 * For terminal-based editors (tmux, nvim), returns false.
 */
export function openInEditor(launcher: LauncherBackend, worktreePath: string): boolean {
  const result = buildEditorLink(launcher, worktreePath);
  if (!result.supportsDeepLink || !result.uri) return false;
  window.open(result.uri, '_blank', 'noopener');
  return true;
}

/**
 * Get the display name for a launcher backend.
 */
export function launcherDisplayName(launcher: LauncherBackend): string {
  switch (launcher) {
    case 'tmux':
      return 'tmux';
    case 'nvim':
      return 'Neovim';
    case 'vscode':
      return 'VS Code';
    case 'cursor':
      return 'Cursor';
    case 'windsurf':
      return 'Windsurf';
    case 'kiro':
      return 'Kiro';
    case 'antigravity':
      return 'Antigravity';
  }
}
