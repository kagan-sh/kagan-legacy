import type { TaskStatus, Priority } from '@/lib/api/types';

export const COLUMN_ORDER: TaskStatus[] = ['BACKLOG', 'IN_PROGRESS', 'REVIEW', 'DONE'];

export const ALLOWED_TASK_TRANSITIONS: Record<TaskStatus, TaskStatus[]> = {
  BACKLOG: ['IN_PROGRESS'],
  IN_PROGRESS: ['BACKLOG', 'REVIEW'],
  REVIEW: ['BACKLOG', 'IN_PROGRESS'],
  DONE: ['BACKLOG'],
};

export const STATUS_LABELS: Record<TaskStatus, string> = {
	BACKLOG: 'Backlog',
	IN_PROGRESS: 'In Progress',
	REVIEW: 'Review',
	DONE: 'Done'
};

export const PRIORITY_LABELS: Record<Priority, string> = {
	LOW: 'Low',
	MEDIUM: 'Medium',
	HIGH: 'High',
	CRITICAL: 'Critical'
};

export const STATUS_COLORS: Record<TaskStatus, string> = {
  BACKLOG: 'var(--kagan-rail-idle)',
  IN_PROGRESS: 'var(--kagan-rail-warning)',
  REVIEW: 'var(--kagan-rail-review)',
  DONE: 'var(--kagan-rail-running)'
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
