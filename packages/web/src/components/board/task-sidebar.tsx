import { InspectorSection } from '@/components/shared/workspace';
import { TaskMetadataPanel } from '@/components/board/task-metadata-panel';
import type { WireTask } from '@/lib/api/types';

interface TaskSidebarProps {
  task: WireTask;
}

export function TaskSidebar({ task }: TaskSidebarProps) {
  const criteria = task.acceptance_criteria ?? [];

  return (
    <div className="space-y-4">
      <TaskMetadataPanel task={task} />

      <InspectorSection title="Review">
        <dl className="space-y-2 text-sm">
          <div className="flex items-center justify-between gap-2">
            <dt className="text-[var(--muted-foreground)]">Approved</dt>
            <dd>{task.review_approved ? 'Yes' : 'No'}</dd>
          </div>
          <div className="flex items-center justify-between gap-2">
            <dt className="text-[var(--muted-foreground)]">Criteria</dt>
            <dd>{criteria.length}</dd>
          </div>
          {task.review_running && (task.review_verdicts ?? []).length === 0 ? (
            <div className="flex items-center justify-between gap-2">
              <dt className="text-[var(--muted-foreground)]">AI Review</dt>
              <dd>Running</dd>
            </div>
          ) : null}
          {(task.review_verdicts ?? []).length > 0 ? (
            <div className="flex items-center justify-between gap-2">
              <dt className="text-[var(--muted-foreground)]">AI Verdict</dt>
              <dd
                className={
                  (task.review_verdicts ?? []).every((v) => v.verdict === 'PASS')
                    ? 'text-[var(--kagan-success)]'
                    : 'text-[var(--destructive)]'
                }
              >
                {(task.review_verdicts ?? []).filter((v) => v.verdict === 'PASS').length}/{(task.review_verdicts ?? []).length} passed
              </dd>
            </div>
          ) : null}
        </dl>
      </InspectorSection>
    </div>
  );
}
