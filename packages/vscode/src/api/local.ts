/**
 * VS Code-local type augmentations.
 *
 * Types and constants that are specific to the VS Code extension and have
 * no equivalent in the shared wire surface (@kagan/shared-api-client).
 */

import type { Priority, TaskStatus } from "@kagan/shared-api-client";

/** Launcher backends supported by the VS Code extension. */
export type LauncherBackend =
  | "tmux"
  | "nvim"
  | "vscode"
  | "cursor"
  | "windsurf"
  | "kiro"
  | "antigravity";

/** VS Code ThemeIcon names by priority. */
export const PRIORITY_ICONS: Record<Priority, string> = {
  LOW: "arrow-down",
  MEDIUM: "dash",
  HIGH: "arrow-up",
  CRITICAL: "flame",
};

/** VS Code ThemeIcon names by task status. */
export const STATUS_ICONS: Record<TaskStatus, string> = {
  BACKLOG: "inbox",
  IN_PROGRESS: "play-circle",
  REVIEW: "eye",
  DONE: "check",
};
