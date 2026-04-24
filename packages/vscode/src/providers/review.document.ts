import type { WireTask } from "../api/types.js";

export interface ReviewDocument {
  text: string;
  criterionLines: Map<string, number>;
  criterionLabels: Map<string, string>;
}

export function buildReviewDocument(task: WireTask | null): ReviewDocument {
  if (!task) {
    return { text: "", criterionLines: new Map(), criterionLabels: new Map() };
  }

  const lines = [
    `# ${task.title}`,
    "",
    `Status: ${task.status}`,
    `Priority: ${task.priority}`,
    `Approved: ${task.review_approved ? "yes" : "no"}`,
    "",
    "## Acceptance Criteria",
    "",
  ];
  const criterionLines = new Map<string, number>();
  const criterionLabels = new Map<string, string>();

  if (task.acceptance_criteria.length === 0) {
    lines.push("1. [ ] No acceptance criteria");
  } else {
    for (const criterion of task.acceptance_criteria) {
      const verdict = task.review_verdicts.find((item) => item.criterion_id === criterion.id);
      const marker =
        verdict?.verdict === "PASS" ? "[PASS]" : verdict?.verdict === "FAIL" ? "[FAIL]" : "[ ]";
      criterionLines.set(criterion.id, lines.length);
      criterionLabels.set(criterion.id, `${criterion.ordinal + 1}`);
      lines.push(`${criterion.ordinal + 1}. ${marker} ${criterion.text}`);
    }
  }

  if (task.review_verdicts.length > 0) {
    const ordinalById = new Map(task.acceptance_criteria.map((c) => [c.id, c.ordinal]));
    lines.push("", "## Verdict Summary", "");
    for (const verdict of task.review_verdicts) {
      const ordinal = ordinalById.get(verdict.criterion_id);
      const label = ordinal !== undefined ? `${ordinal + 1}` : verdict.criterion_id;
      lines.push(`${label}. ${verdict.verdict}: ${verdict.reason}`);
    }
  }

  return { text: lines.join("\n"), criterionLines, criterionLabels };
}
