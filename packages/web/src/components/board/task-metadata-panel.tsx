import type { ReactNode } from 'react';
import { Workflow } from 'lucide-react';
import { InspectorSection } from '@/components/shared/workspace';
import type { TaskStatus, WireTask } from '@/lib/api/types';
import { cn } from '@/lib/utils';
import { STATUS_LABELS } from '@/lib/utils/constants';

export interface TaskMetadataRow {
  label: string;
  value: ReactNode;
  labelClassName?: string;
  valueClassName?: string;
  rowClassName?: string;
  icon?: ReactNode;
}

interface TaskMetadataPanelProps {
  task: WireTask;
  runtimeTitle?: string;
  taskDataTitle?: string;
  runtimeRows?: TaskMetadataRow[];
  taskDataRows?: TaskMetadataRow[];
  showRuntimeSection?: boolean;
  showTaskDataSection?: boolean;
  workspaceReadyLabel?: string;
  workspaceNotReadyLabel?: string;
  statusLabel?: string;
  statusValue?: ReactNode;
  branchValue?: ReactNode;
}

export function TaskMetadataPanel({
  task,
  runtimeTitle = 'Runtime',
  taskDataTitle = 'Task Data',
  runtimeRows,
  taskDataRows,
  showRuntimeSection = true,
  showTaskDataSection = true,
  workspaceReadyLabel = 'Ready',
  workspaceNotReadyLabel = 'Not provisioned',
  statusLabel = 'Status',
  statusValue,
  branchValue,
}: TaskMetadataPanelProps) {
  const resolvedRuntimeRows =
    runtimeRows ??
    [
      {
        label: 'Workspace',
        value: task.has_workspace ? workspaceReadyLabel : workspaceNotReadyLabel,
      },
      {
        label: 'Active session',
        value: task.active_session ? task.active_session.status : 'Idle',
      },
      {
        label: 'Last event',
        value: task.last_event_at ? new Date(task.last_event_at).toLocaleString() : 'No events yet',
        valueClassName: 'text-right',
      },
    ];

  const resolvedTaskDataRows =
    taskDataRows ??
    [
      {
        label: statusLabel,
        value: statusValue ?? STATUS_LABELS[task.status as TaskStatus] ?? task.status,
        icon: <Workflow className="size-4" />,
        labelClassName: 'inline-flex items-center gap-2 text-[var(--muted-foreground)]',
      },
      {
        label: 'Launcher',
        value: task.launcher || 'Default',
      },
      {
        label: 'Agent backend',
        value: task.agent_backend || 'Default',
        valueClassName: 'text-right',
      },
      {
        label: 'Base branch',
        value: branchValue ?? task.base_branch ?? 'Project default',
      },
    ];

  return (
    <>
      {showRuntimeSection ? <MetadataSection title={runtimeTitle} rows={resolvedRuntimeRows} /> : null}
      {showTaskDataSection ? <MetadataSection title={taskDataTitle} rows={resolvedTaskDataRows} /> : null}
    </>
  );
}

function MetadataSection({ title, rows }: { title: string; rows: TaskMetadataRow[] }) {
  return (
    <InspectorSection title={title}>
      <dl className="space-y-2 text-sm">
        {rows.map((row, index) => (
          <div key={`${row.label}-${index}`} className={cn('flex items-center justify-between gap-2', row.rowClassName)}>
            <dt className={cn('text-[var(--muted-foreground)]', row.labelClassName)}>
              {row.icon ? (
                <span className="inline-flex items-center gap-2">
                  {row.icon}
                  {row.label}
                </span>
              ) : (
                row.label
              )}
            </dt>
            <dd className={row.valueClassName}>{row.value}</dd>
          </div>
        ))}
      </dl>
    </InspectorSection>
  );
}
