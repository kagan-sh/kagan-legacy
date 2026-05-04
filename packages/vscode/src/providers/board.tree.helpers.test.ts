import { describe, expect, it } from "vitest";
import type { TaskStatus, WireTask } from "@kagan/shared-api-client";
import { groupTasksByStatus, sortTasksByTitle, TASK_COLUMN_LABELS } from "./board.tree.helpers.js";

function task(id: string, title: string, status: TaskStatus): WireTask {
  return {
    id,
    title,
    description: "",
    status,
    priority: "MEDIUM",
    base_branch: null,
    acceptance_criteria: [],
    agent_backend: null,
    launcher: null,
    review_approved: false,
    review_verdicts: [],
    updated_at: null,
    last_event_at: null,
    has_workspace: false,
    review_running: false,
    active_session: null,
  };
}

describe("board tree helpers", () => {
  it("groups tasks into every visible board column", () => {
    const grouped = groupTasksByStatus([
      task("task-1", "First", "BACKLOG"),
      task("task-2", "Second", "DONE"),
      task("task-3", "Third", "BACKLOG"),
    ]);

    expect(grouped.get("BACKLOG")?.map((item) => item.id)).toEqual(["task-1", "task-3"]);
    expect(grouped.get("IN_PROGRESS")).toEqual([]);
    expect(grouped.get("REVIEW")).toEqual([]);
    expect(grouped.get("DONE")?.map((item) => item.id)).toEqual(["task-2"]);
  });

  it("sorts task rows by title without mutating the source list", () => {
    const source = [
      task("task-b", "Zebra", "BACKLOG"),
      task("task-a", "Alpha", "BACKLOG"),
    ];

    expect(sortTasksByTitle(source).map((item) => item.id)).toEqual(["task-a", "task-b"]);
    expect(source.map((item) => item.id)).toEqual(["task-b", "task-a"]);
  });

  it("keeps command labels and board labels on the same source of truth", () => {
    expect(TASK_COLUMN_LABELS).toEqual({
      BACKLOG: "Backlog",
      IN_PROGRESS: "In Progress",
      REVIEW: "Review",
      DONE: "Done",
    });
  });
});
