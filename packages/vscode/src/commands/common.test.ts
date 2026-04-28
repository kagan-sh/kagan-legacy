import { describe, expect, it, vi } from "vitest";
import type { WireTask } from "../api/types.js";

const showErrorMessage = vi.fn();
const showWarningMessage = vi.fn();

vi.mock("vscode", () => ({
  window: {
    showErrorMessage: (...args: unknown[]) => showErrorMessage(...args),
    showWarningMessage: (...args: unknown[]) => showWarningMessage(...args),
  },
}));

import {
  confirmAction,
  formatCommandError,
  isTaskItem,
  taskPickItems,
  withErrors,
} from "./common.js";

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

  describe("withErrors", () => {
    it("calls run() and surfaces nothing when it succeeds", async () => {
      showErrorMessage.mockClear();
      const ran = vi.fn().mockResolvedValue(undefined);
      await withErrors("run task", ran);
      expect(ran).toHaveBeenCalledTimes(1);
      expect(showErrorMessage).not.toHaveBeenCalled();
    });

    it("shows a formatted error toast when run() throws", async () => {
      showErrorMessage.mockClear();
      const ran = vi.fn().mockRejectedValue(new Error("boom"));
      await withErrors("delete task", ran);
      expect(showErrorMessage).toHaveBeenCalledWith("Failed to delete task: boom");
    });

    it("swallows the rejection so the caller never sees it", async () => {
      showErrorMessage.mockClear();
      await expect(
        withErrors("flaky", () => Promise.reject(new Error("nope"))),
      ).resolves.toBeUndefined();
    });
  });

  describe("confirmAction", () => {
    it("returns true when the user picks the action label", async () => {
      showWarningMessage.mockResolvedValueOnce("Delete");
      await expect(confirmAction("Are you sure?", "Delete")).resolves.toBe(true);
      expect(showWarningMessage).toHaveBeenCalledWith(
        "Are you sure?",
        { modal: true },
        "Delete",
      );
    });

    it("returns false when the user dismisses the prompt", async () => {
      showWarningMessage.mockResolvedValueOnce(undefined);
      await expect(confirmAction("Are you sure?", "Delete")).resolves.toBe(false);
    });
  });
});
