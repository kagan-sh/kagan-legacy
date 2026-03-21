import { useState, useCallback, useEffect } from 'react';
import { CheckCircle, GitMerge, GitPullRequestArrow, Loader2, XCircle } from 'lucide-react';
import { apiClient } from '@/lib/api/client';
import { useSetAtom } from 'jotai';
import { fetchTasksAtom } from '@/lib/atoms/board';
import { toast } from 'sonner';
import type { WireTask } from '@/lib/api/types';
import { Button } from '@/components/ui/button';
import { Textarea } from '@/components/ui/textarea';
import { isEditableTarget, hasOpenOverlay } from '@/lib/utils/dom';

interface ReviewPanelProps {
  taskId: string;
  task?: WireTask;
  className?: string;
  enableHotkeys?: boolean;
}

export function ReviewPanel({ taskId, task, className, enableHotkeys = false }: ReviewPanelProps) {
  const fetchTasks = useSetAtom(fetchTasksAtom);
  const [feedback, setFeedback] = useState('');
  const [loading, setLoading] = useState(false);
  const criteriaCount = (task?.acceptance_criteria ?? []).filter((criterion) => criterion.trim()).length;
  const canRunReview = task?.status === 'REVIEW' && criteriaCount > 0;

  const handleAction = useCallback(
    async (action: 'approve' | 'reject' | 'merge' | 'rebase' | 'run_review') => {
      setLoading(true);
      try {
        if (action === 'run_review') {
          await apiClient.runReview(taskId);
          toast.success('AI review started');
        } else {
          await apiClient.reviewDecide(taskId, {
            action,
            feedback: feedback || undefined,
          });
          const pastTense: Record<'approve' | 'reject' | 'merge' | 'rebase', string> = {
            approve: 'approved',
            reject: 'rejected',
            merge: 'merged',
            rebase: 'rebased',
          };
          toast.success(`Task ${pastTense[action]}`);
        }
        fetchTasks();
        setFeedback('');
      } catch (error) {
        const label = action === 'run_review' ? 'start AI review' : action;
        toast.error(error instanceof Error ? error.message : `Failed to ${label}`);
      } finally {
        setLoading(false);
      }
    },
    [taskId, feedback, fetchTasks],
  );

  useEffect(() => {
    if (!enableHotkeys) return;

    const onKeyDown = (event: KeyboardEvent) => {
      if (loading || isEditableTarget(event.target)) {
        return;
      }

      if (hasOpenOverlay()) {
        return;
      }

      const lowerKey = event.key.toLowerCase();
      if (lowerKey === 'a') {
        event.preventDefault();
        void handleAction('approve');
        return;
      }
      if (lowerKey === 'x') {
        event.preventDefault();
        void handleAction('reject');
        return;
      }
      if (lowerKey === 'm') {
        event.preventDefault();
        void handleAction('merge');
        return;
      }
      if (lowerKey === 'b') {
        event.preventDefault();
        void handleAction('rebase');
      }
    };

    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [enableHotkeys, handleAction, loading]);

  return (
    <div className={className}>
      {task?.review_verdicts && task.review_verdicts.length > 0 ? (
        <div className="mb-4 space-y-2">
          <h3 className="text-base font-semibold">AI Verdict</h3>
          <div className="space-y-1.5">
            {task.review_verdicts.map((v) => (
              <div key={v.criterion_index} className="flex items-start gap-2 text-sm">
                {v.verdict === 'PASS' ? (
                  <CheckCircle className="mt-0.5 size-3.5 text-[var(--kagan-success)]" />
                ) : (
                  <XCircle className="mt-0.5 size-3.5 text-[var(--destructive)]" />
                )}
                <div className="min-w-0">
                  <span className="font-medium">{(task.acceptance_criteria ?? [])[v.criterion_index] ?? `Criterion ${v.criterion_index + 1}`}</span>
                  <p className="text-[var(--muted-foreground)]">{v.reason}</p>
                </div>
              </div>
            ))}
          </div>
        </div>
      ) : task?.review_running ? (
        <div className="mb-4 flex items-center gap-2 text-sm text-[var(--muted-foreground)]">
          <Loader2 className="size-4 animate-spin" />
          AI Reviewing...
        </div>
      ) : null}
      <div className="mb-4">
        <h3 className="text-base font-semibold">Review Decisions</h3>
        <p className="mt-1 text-sm text-[var(--muted-foreground)]">
          Approve, reject, or merge once the agent output satisfies the current acceptance criteria.
        </p>
        {!canRunReview ? (
          <p className="mt-2 text-sm text-[var(--muted-foreground)]">
            Add at least one acceptance criterion before running or approving AI review.
          </p>
        ) : null}
      </div>
      <Textarea
        value={feedback}
        onChange={(e) => setFeedback(e.target.value)}
        placeholder="Optional feedback..."
        rows={3}
        className="mb-4 min-h-28 border-[color:var(--border-subtle)] bg-[color:var(--surface-0)]"
      />
      <div className="flex flex-wrap gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => handleAction('run_review')}
          disabled={loading || !canRunReview || Boolean(task?.review_running)}
        >
          <Loader2 className={`size-3 ${task?.review_running ? 'animate-spin' : ''}`} />
          Run AI Review
        </Button>
        <Button
          size="sm"
          onClick={() => handleAction('approve')}
          disabled={loading || !canRunReview}
          className=" bg-[var(--kagan-success)] text-white hover:bg-[var(--kagan-success)]/90"
        >
          <CheckCircle className="size-3" />
          Approve
        </Button>
        <Button
          variant="destructive"
          size="sm"
          onClick={() => handleAction('reject')}
          disabled={loading}
          className=""
        >
          <XCircle className="size-3" />
          Reject
        </Button>
        <Button
          size="sm"
          onClick={() => handleAction('merge')}
          disabled={loading || !canRunReview}
          className=""
        >
          <GitMerge className="size-3" />
          Merge
        </Button>
        <Button
          variant="outline"
          size="sm"
          onClick={() => handleAction('rebase')}
          disabled={loading}
          className=""
        >
          <GitPullRequestArrow className="size-3" />
          Rebase
        </Button>
      </div>
    </div>
  );
}
