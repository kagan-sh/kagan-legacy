/**
 * VS Code-local type augmentations.
 *
 * Types and constants that are specific to the VS Code extension and have
 * no equivalent in the shared wire surface (@kagan/shared-api-client).
 */

import type { Priority, TaskStatus } from "@kagan/shared-api-client";

// ── Frame stream event name constants ────────────────────────────────────────
// Derived from the Frame discriminated union type in wire.ts:
//   FrameSnapshot.type = 'snapshot'
//   FrameReady.type    = 'ready'
//   FramePatch.type    = 'patch'
//   FrameResume.type   = 'resume'
//
// Used as the SSE event name when subscribing via addEventListener.
// Never hand-type these strings — use FRAME_EVENT consts.

export const FRAME_EVENT = {
  SNAPSHOT: "snapshot",
  READY: "ready",
  PATCH: "patch",
  RESUME: "resume",
} as const satisfies Record<string, "snapshot" | "ready" | "patch" | "resume">;

export type FrameEventName = (typeof FRAME_EVENT)[keyof typeof FRAME_EVENT];

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
