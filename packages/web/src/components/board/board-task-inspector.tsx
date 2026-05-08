import { Activity, ArrowUpRight, Copy, Pencil, Plus, X } from 'lucide-react';
import { EVENT_TYPE } from '@kagan/shared-api-client';
import type { TaskStatus, WireEvent, WireTask } from '@kagan/shared-api-client';
import { useTaskEvents } from '@/lib/hooks/use-task-events';
import { STATUS_LABELS } from '@/lib/utils/constants';
import { AgentControl } from '@/components/board/agent-control';
import { TaskMetadataPanel } from '@/components/board/task-metadata-panel';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { ScrollArea } from '@/components/ui/scroll-area';
import { InspectorSection, Panel } from '@/components/shared/workspace';
import { cn } from '@/lib/utils';

interface BoardTaskActions {
  onOpenTask: () => void;
  onOpenStream: () => void;
  onEdit?: () => void;
}

interface BoardTaskInspectorProps extends BoardTaskActions {
  task: WireTask;
  className?: string;
  onClose?: () => void;
}

/** Event types worth surfacing in the board-level activity summary. */
const INSPECTOR_EVENT_TYPES: ReadonlySet<string> = new Set([
  EVENT_TYPE.TASK_STATUS_CHANGED,
  EVENT_TYPE.PLAN_UPDATE,
  EVENT_TYPE.AGENT_COMPLETED,
  EVENT_TYPE.AGENT_FAILED,
  EVENT_TYPE.AUTO_REVIEW_STARTED,
  EVENT_TYPE.CRITERION_VERDICT,
  EVENT_TYPE.MERGE_COMPLETED,
  EVENT_TYPE.MERGE_FAILED,
]);

function formatEventSummary(event: WireEvent) {
  if (event.type === EVENT_TYPE.TASK_STATUS_CHANGED) {
    const from = typeof event.payload?.from === 'string' ? event.payload.from : '?';
    const to = typeof event.payload?.to === 'string' ? event.payload.to : '?';
    return `Status changed from ${from.replaceAll('_', ' ')} to ${to.replaceAll('_', ' ')}`;
  }
  if (event.type === EVENT_TYPE.PLAN_UPDATE) return 'Execution plan updated';
  if (event.type === EVENT_TYPE.AGENT_COMPLETED) return 'Agent completed the current run';
  if (event.type === EVENT_TYPE.AUTO_REVIEW_STARTED) return 'Auto-review started';
  if (event.type === EVENT_TYPE.AGENT_FAILED) return 'Agent reported a failure';
  if (event.type === EVENT_TYPE.CRITERION_VERDICT) {
    const criterion = typeof event.payload?.criterion === 'string' ? event.payload.criterion : '';
    const passed = event.payload?.passed;
    return criterion ? `Criterion ${passed ? 'passed' : 'failed'}: ${criterion}` : 'Criterion verdict';
  }
  if (event.type === EVENT_TYPE.MERGE_COMPLETED) return 'Merge completed';
  if (event.type === EVENT_TYPE.MERGE_FAILED) return 'Merge failed';
  return event.type.replaceAll('_', ' ').toLowerCase();
}

function TaskStatusBadge({ task }: { task: WireTask }) {
  return (
    <div className="flex flex-wrap gap-2">
      <Badge variant="outline" className=" px-2.5 py-1 font-code text-[10px] uppercase tracking-[0.16em]">
        {STATUS_LABELS[task.status as TaskStatus] ?? task.status}
      </Badge>
      <Badge variant="outline" className=" px-2.5 py-1 font-code text-[10px] uppercase tracking-[0.16em]">
        {task.active_session ? 'Live session' : 'Idle'}
      </Badge>
    </div>
  );
}

function TaskSnapshotBody({ task, onOpenTask, onOpenStream, onEdit }: BoardTaskInspectorProps) {
  const { events, runningSince } = useTaskEvents(task.id, { initialLimit: 18, pollInterval: 5000 });
  const criteria = task.acceptance_criteria ?? [];
  const recentEvents = events.filter((e) => INSPECTOR_EVENT_TYPES.has(e.type)).slice(-6).reverse();

  return (
    <div className="space-y-4">
      <InspectorSection
        title="Quick Actions"
      >
        <div className="flex flex-wrap gap-2">
          <AgentControl
            taskId={task.id}
            status={task.status}
            startedAt={runningSince}
            taskLauncher={task.launcher}
            activeSessionId={task.active_session?.id ?? null}
            activeSessionLauncher={task.active_session?.launcher ?? null}
          />
          {task.active_session ? (
            <>
              <Button size="sm" className="cta-glow" onClick={onOpenStream}>
                <Activity className="size-4" />
                Watch task stream
              </Button>
              <Button size="sm" variant="ghost" className=" text-[var(--muted-foreground)] hover:text-[var(--foreground)]" onClick={onOpenTask}>
                <ArrowUpRight className="size-4" />
                Open task
              </Button>
            </>
          ) : (
            <Button size="sm" className="cta-glow" onClick={onOpenTask}>
              <ArrowUpRight className="size-4" />
              Open task
            </Button>
          )}
          {onEdit ? (
            <Button size="sm" variant="ghost" className=" text-[var(--muted-foreground)] hover:text-[var(--foreground)]" onClick={onEdit}>
              <Pencil className="size-4" />
              Edit
            </Button>
          ) : null}
        </div>
      </InspectorSection>

      <InspectorSection title="Description">
        {task.description ? (
          <p className="text-sm leading-6 text-[var(--muted-foreground)]">{task.description}</p>
        ) : (
          <Button
            type="button"
            variant="ghost"
            className="h-auto px-3 py-1.5 text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
            onClick={() => onEdit?.()}
            disabled={!onEdit}
          >
            <Plus className="size-4" />
            Add Description
          </Button>
        )}
      </InspectorSection>

      <InspectorSection title="Acceptance Criteria">
        {criteria.length > 0 ? (
          <div className="space-y-2">
            {criteria.map((criterion) => (
              <div
                key={criterion.id}
                className=" border border-[color:var(--border-subtle)] bg-[color:var(--surface-0)] px-3 py-2 text-sm text-[var(--muted-foreground)]"
              >
                {criterion.text}
              </div>
            ))}
          </div>
        ) : (
          <Button
            type="button"
            variant="ghost"
            className="h-auto px-3 py-1.5 text-sm text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
            onClick={() => onEdit?.()}
            disabled={!onEdit}
          >
            <Plus className="size-4" />
            Add Acceptance Criteria
          </Button>
        )}
      </InspectorSection>

      <TaskMetadataPanel
        task={task}
        runtimeRows={[
          { label: 'Workspace', value: task.has_workspace ? 'Provisioned' : 'Not provisioned' },
          { label: 'Session', value: task.active_session?.status || 'Idle' },
          { label: 'Base branch', value: task.base_branch || 'Project default' },
        ]}
        showTaskDataSection={false}
      />

      <InspectorSection title="Recent Activity">
        {recentEvents.length > 0 ? (
          <div className="space-y-0.5">
            {recentEvents.map((event) => (
              <div
                key={event.id}
                className="flex items-start gap-2 border-l-2 border-[color:var(--border-subtle)] py-1.5 pl-3"
              >
                <p className="min-w-0 flex-1 text-sm leading-5 text-[var(--foreground)]">
                  {formatEventSummary(event)}
                </p>
                <span className="shrink-0 pt-0.5 font-code text-[10px] text-[var(--muted-foreground)]">
                  {new Date(event.created_at).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <p className="text-sm text-[var(--muted-foreground)]">No events yet.</p>
        )}
      </InspectorSection>
    </div>
  );
}

export function BoardTaskInspector({ task, className, onOpenTask, onOpenStream, onEdit, onClose }: BoardTaskInspectorProps) {
  return (
    <Panel className={cn('flex flex-col', className)}>
      <div className="border-b border-[color:var(--border-subtle)] px-5 py-4">
        <div className="flex items-start justify-between gap-3">
          <p className="font-code text-[11px] uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
            Task Inspector
          </p>
          {onClose ? (
            <button
              type="button"
              onClick={onClose}
              className="inline-flex size-6 items-center justify-center text-[var(--muted-foreground)] transition-colors hover:bg-[color:var(--surface-2)] hover:text-[var(--foreground)]"
              aria-label="Close inspector"
            >
              <X className="size-4" />
            </button>
          ) : null}
        </div>
        <div className="mt-2 space-y-2">
          <h2 className="text-lg font-semibold text-[var(--foreground)]">{task.title}</h2>
          <div className="group inline-flex items-center gap-1.5 px-1 py-0.5 font-code text-[10px] uppercase tracking-[0.14em] text-[var(--muted-foreground)]">
            <span>{task.id}</span>
            <button
              type="button"
              className="inline-flex size-5 items-center justify-center text-[var(--muted-foreground)] opacity-50 transition-opacity hover:opacity-100 focus-visible:opacity-100 focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--primary)]"
              onClick={() => {
                void navigator.clipboard.writeText(task.id).then(() => undefined, () => undefined);
              }}
              aria-label="Copy task ID"
            >
              <Copy className="size-3" />
            </button>
          </div>
          <TaskStatusBadge task={task} />
        </div>
      </div>
      <div className="min-h-0 flex-1">
        <ScrollArea className="h-full">
          <div className="space-y-4 px-5 py-4">
            <TaskSnapshotBody
              task={task}
              onOpenTask={onOpenTask}
              onOpenStream={onOpenStream}
              onEdit={onEdit}
            />
          </div>
        </ScrollArea>
      </div>
    </Panel>
  );
}
