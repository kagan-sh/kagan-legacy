import { InspectorSection } from '@/components/shared/workspace';
import { TaskMetadataPanel } from '@/components/board/task-metadata-panel';
import type { WireTask } from '@kagan/shared-api-client';

interface TaskSidebarProps {
  task: WireTask;
}

type ReviewSidebarSummary = {
  criteriaCoverage: string;
  evidenceState: string;
  decisionState: string;
  approvalState: string;
};

export function TaskSidebar({ task }: TaskSidebarProps) {
  const summary = buildReviewSidebarSummary(task);

  return (
    <div className="space-y-4">
      <TaskMetadataPanel task={task} />

      <InspectorSection title="Review">
        <dl className="space-y-3 text-sm">
          <div className="flex items-center justify-between gap-2">
            <dt className="text-[var(--muted-foreground)]">Approval</dt>
            <dd className={summary.approvalState === 'Approved' ? 'text-[var(--kagan-success)]' : ''}>
              {summary.approvalState}
            </dd>
          </div>
          <div className="flex items-center justify-between gap-2">
            <dt className="text-[var(--muted-foreground)]">Criteria coverage</dt>
            <dd>{summary.criteriaCoverage}</dd>
          </div>
          <div className="flex items-center justify-between gap-2">
            <dt className="text-[var(--muted-foreground)]">AI review</dt>
            <dd>{summary.evidenceState}</dd>
          </div>
          <div className="flex items-center justify-between gap-2">
            <dt className="text-[var(--muted-foreground)]">Before merge</dt>
            <dd>{summary.decisionState}</dd>
          </div>
        </dl>
      </InspectorSection>
    </div>
  );
}

function buildReviewSidebarSummary(task: WireTask): ReviewSidebarSummary {
  const criteriaCount = (task.acceptance_criteria ?? []).filter((c) => c.text.trim()).length;
  const verdicts = task.review_verdicts ?? [];
  const reviewedCount = Math.min(verdicts.length, criteriaCount);
  const passedCount = verdicts.filter((verdict) => verdict.verdict === 'PASS').length;
  const failedCount = verdicts.length - passedCount;

  const criteriaCoverage =
    criteriaCount === 0
      ? 'No criteria yet'
      : `${reviewedCount}/${criteriaCount} reviewed`;

  const evidenceState = task.review_running
    ? 'Running'
    : verdicts.length > 0
      ? `${passedCount} pass, ${failedCount} fail`
      : 'Not run yet';

  const approvalState = task.review_approved ? 'Approved' : 'Pending';

  const decisionState = task.review_approved
    ? 'Ready to merge'
    : criteriaCount === 0
      ? 'Add acceptance criteria'
      : failedCount > 0
        ? 'Resolve failing criteria'
        : task.review_running
          ? 'Review in progress'
          : reviewedCount > 0
            ? 'Approve to continue'
            : 'Awaiting approval';

  return {
    criteriaCoverage,
    evidenceState,
    decisionState,
    approvalState,
  };
}
