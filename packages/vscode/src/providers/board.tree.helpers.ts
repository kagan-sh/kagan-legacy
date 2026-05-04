import { TASK_COLUMNS, type TaskStatus, type WireTask } from "@kagan/shared-api-client";

export const TASK_COLUMN_LABELS: Record<TaskStatus, string> = {
  BACKLOG: "Backlog",
  IN_PROGRESS: "In Progress",
  REVIEW: "Review",
  DONE: "Done",
};

export function groupTasksByStatus(tasks: WireTask[]): Map<TaskStatus, WireTask[]> {
  const groups = new Map<TaskStatus, WireTask[]>();
  for (const status of TASK_COLUMNS) {
    groups.set(status, []);
  }
  for (const task of tasks) {
    groups.get(task.status as TaskStatus)?.push(task);
  }
  return groups;
}

export function sortTasksByTitle(tasks: WireTask[]): WireTask[] {
  return [...tasks].sort((left, right) => left.title.localeCompare(right.title));
}
