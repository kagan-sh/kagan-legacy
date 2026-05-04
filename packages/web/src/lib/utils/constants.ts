import type { TaskStatus, Priority } from '@kagan/shared-api-client';

export const COLUMN_ORDER: TaskStatus[] = ['BACKLOG', 'IN_PROGRESS', 'REVIEW', 'DONE'];

export const ALLOWED_TASK_TRANSITIONS: Record<TaskStatus, TaskStatus[]> = {
  BACKLOG: ['IN_PROGRESS'],
  IN_PROGRESS: ['BACKLOG', 'REVIEW'],
  REVIEW: ['BACKLOG', 'IN_PROGRESS'],
  DONE: ['BACKLOG'],
};

// CANCELLED is a session-level status that may appear in task streams even though
// the wire TaskStatus union does not include it yet. The wider type lets consumers
// look it up without a cast while keeping the Record strict for the known four.
export const STATUS_LABELS: Record<TaskStatus, string> & Record<string, string> = {
	BACKLOG: 'Backlog',
	IN_PROGRESS: 'In Progress',
	REVIEW: 'Review',
	DONE: 'Done',
	CANCELLED: 'Cancelled',
};

export const PRIORITY_LABELS: Record<Priority, string> = {
	LOW: 'Low',
	MEDIUM: 'Medium',
	HIGH: 'High',
	CRITICAL: 'Critical'
};

export const PRIORITY_GLYPHS: Record<Priority, string> = {
	LOW: '▼',
	MEDIUM: '—',
	HIGH: '▲',
	CRITICAL: '▲',
};

export const STATUS_COLORS: Record<TaskStatus, string> & Record<string, string> = {
  BACKLOG: 'var(--kagan-rail-idle)',
  IN_PROGRESS: 'var(--kagan-rail-warning)',
  REVIEW: 'var(--kagan-rail-review)',
  DONE: 'var(--kagan-rail-running)',
  // CANCELLED collapses into DONE column; shown with idle (neutral) colour.
  CANCELLED: 'var(--kagan-rail-idle)',
};

export function getAllowedTaskTransitions(status: TaskStatus): TaskStatus[] {
  return ALLOWED_TASK_TRANSITIONS[status];
}

export function isAllowedTaskTransition(from: TaskStatus, to: TaskStatus): boolean {
  return ALLOWED_TASK_TRANSITIONS[from].includes(to);
}

export const LAUNCHER_OPTIONS = [
  'tmux',
  'nvim',
  'vscode',
  'cursor',
  'windsurf',
  'kiro',
  'antigravity',
] as const;

export type SortOption = 'default' | 'created' | 'priority' | 'recent';

export const SORT_LABELS: Record<SortOption, string> = {
  default: 'Default',
  created: 'Created',
  priority: 'Priority',
  recent: 'Recent Activity',
};
