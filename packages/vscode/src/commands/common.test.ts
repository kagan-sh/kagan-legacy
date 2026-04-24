import { describe, expect, it, vi } from "vitest";
import type { WireTask } from "../api/types.js";

vi.mock("vscode", () => ({}));

import { formatCommandError, isTaskItem, taskPickItems } from "./common.js";

function task(overrides: Partial<WireTask> = {}): WireTask {
  return {
    id: "task-1",
    title: "Review login",
    description: "Check the login path",
    status: "REVIEW",
    priority: "HIGH",
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
    ...overrides,
  };
}

describe("command helpers", () => {
  it("recognizes tree task items structurally", () => {
    expect(isTaskItem({ kind: "task", task: task() })).toBe(true);
    expect(isTaskItem({ kind: "column", status: "REVIEW", count: 1 })).toBe(false);
    expect(isTaskItem(null)).toBe(false);
  });

  it("builds task quick-pick rows with optional status metadata", () => {
    expect(taskPickItems([task()])).toEqual([
      {
        label: "Review login",
        description: "REVIEW · HIGH",
        detail: "Check the login path",
        task: task(),
      },
    ]);

    expect(taskPickItems([task()], { showStatusAndPriority: false })[0]?.description).toBeUndefined();
  });

  it("formats command failures consistently", () => {
    expect(formatCommandError("run task", new Error("server offline"))).toBe(
      "Failed to run task: server offline",
    );
    expect(formatCommandError("run task", "unknown")).toBe("Failed to run task: unknown");
  });
});
