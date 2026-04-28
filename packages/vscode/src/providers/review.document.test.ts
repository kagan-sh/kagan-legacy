import { describe, expect, it } from "vitest";
import type { WireTask } from "../api/types.js";
import { buildReviewDocument } from "./review.document.js";

function task(overrides: Partial<WireTask> = {}): WireTask {
  return {
    id: "task-1",
    title: "Ship review flow",
    description: "",
    status: "REVIEW",
    priority: "HIGH",
    base_branch: "main",
    acceptance_criteria: [
      { id: "criterion-a", task_id: "task-1", ordinal: 0, text: "Show verdicts" },
      { id: "criterion-b", task_id: "task-1", ordinal: 1, text: "Keep comments aligned" },
    ],
    agent_backend: "claude-code",
    launcher: null,
    review_approved: false,
    review_verdicts: [
      {
        id: "verdict-a",
        criterion_id: "criterion-a",
        session_id: null,
        verdict: "PASS",
        reason: "The document renders the passing row.",
      },
    ],
    updated_at: null,
    last_event_at: null,
    has_workspace: false,
    review_running: false,
    active_session: null,
    ...overrides,
  };
}

// markerForVerdict is an internal helper but its behaviour is observable
// through buildReviewDocument — drive it through the public surface.
describe("markerForVerdict (via buildReviewDocument)", () => {
  it("renders [SKIP] for a SKIP verdict", () => {
    const document = buildReviewDocument(
      task({
        review_verdicts: [
          {
            id: "verdict-a",
            criterion_id: "criterion-a",
            session_id: null,
            verdict: "SKIP",
            reason: "Skipped intentionally.",
          },
        ],
      }),
    );
    expect(document.text).toContain("1. [SKIP] Show verdicts");
  });

  it("renders [?] for an unrecognised verdict value", () => {
    const document = buildReviewDocument(
      task({
        review_verdicts: [
          {
            id: "verdict-a",
            criterion_id: "criterion-a",
            session_id: null,
            // Cast to simulate an unknown wire value arriving at runtime.
            verdict: "UNKNOWN" as "PASS",
            reason: "Unknown verdict from wire.",
          },
        ],
      }),
    );
    expect(document.text).toContain("1. [?] Show verdicts");
  });
});

describe("buildReviewDocument", () => {
  it("renders acceptance criteria and exposes stable comment line metadata", () => {
    const document = buildReviewDocument(task());

    expect(document.text).toContain("1. [PASS] Show verdicts");
    expect(document.text).toContain("2. [ ] Keep comments aligned");
    expect(document.criterionLines.get("criterion-a")).toBe(8);
    expect(document.criterionLabels.get("criterion-b")).toBe("2");
  });

  it("renders a no-criteria placeholder without comment anchors", () => {
    const document = buildReviewDocument(
      task({
        acceptance_criteria: [],
        review_verdicts: [],
      }),
    );

    expect(document.text).toContain("1. [ ] No acceptance criteria");
    expect(document.criterionLines.size).toBe(0);
  });
});
