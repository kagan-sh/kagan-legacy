import { describe, expect, it, vi } from "vitest";

// vscode must be mocked before importing any module that imports it.
// vi.mock is hoisted — factory cannot reference outer-scope variables.
vi.mock("vscode", () => ({
  comments: { createCommentController: vi.fn() },
  CommentMode: { Preview: 0 },
  CommentThreadState: { Resolved: 1, Unresolved: 0 },
  MarkdownString: class {
    constructor(public value: string) {}
  },
  Uri: { from: vi.fn() },
  window: { showTextDocument: vi.fn() },
  Range: class {
    constructor(
      public startLine: number,
      public startChar: number,
      public endLine: number,
      public endChar: number,
    ) {}
  },
  EventEmitter: class {
    event = vi.fn();
    fire = vi.fn();
    dispose = vi.fn();
  },
}));

import { iconForVerdict } from "./review.comments.js";

describe("iconForVerdict", () => {
  it("returns $(pass) for PASS", () => {
    expect(iconForVerdict("PASS")).toBe("$(pass)");
  });

  it("returns $(error) for FAIL", () => {
    expect(iconForVerdict("FAIL")).toBe("$(error)");
  });

  it("returns $(circle-slash) for SKIP", () => {
    expect(iconForVerdict("SKIP")).toBe("$(circle-slash)");
  });

  it("returns $(question) for an unknown verdict value", () => {
    expect(iconForVerdict("UNKNOWN")).toBe("$(question)");
  });
});
