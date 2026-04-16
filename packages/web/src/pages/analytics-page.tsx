import { useCallback, useEffect, useMemo, useState } from 'react';
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts';
import type { ValueType } from 'recharts/types/component/DefaultTooltipContent';
import {
  Activity,
  BarChart3,
  Clock,
  Download,
  Grid3x3,
  HelpCircle,
  TrendingUp,
  Users,
} from 'lucide-react';
import { apiClient } from '@/lib/api/client';
import type {
  BackendStats,
  CombinedStats,
  RoleStats,
  SessionTimelineEntry,
  TaskTypeStats,
} from '@/lib/api/types';
import { formatDuration, formatPercentage } from '@/lib/format';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';

// ---------------------------------------------------------------------------
// Chart colours — using CSS custom properties where possible
// ---------------------------------------------------------------------------

const CHART_COLORS = {
  completed: 'var(--status-running, #22c55e)',
  failed: 'var(--status-error, #ef4444)',
  cancelled: 'var(--muted-foreground, #6b7280)',
  pending: 'var(--status-idle, #3b82f6)',
  running: 'var(--status-warning, #f59e0b)',
  accent: 'var(--primary, #d4a84b)',
};

const BACKEND_PALETTE = [
  '#6366f1', '#8b5cf6', '#d946ef', '#ec4899', '#f43f5e',
  '#f97316', '#eab308', '#22c55e', '#14b8a6', '#06b6d4',
  '#3b82f6', '#2563eb', '#a855f7', '#84cc16',
];

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function shortDate(iso: string): string {
  const d = new Date(iso);
  return d.toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

// ---------------------------------------------------------------------------
// KPI Card
// ---------------------------------------------------------------------------

function KpiCard({
  label,
  value,
  icon: Icon,
  subtitle,
}: {
  label: string;
  value: string;
  icon: React.ElementType;
  subtitle?: string;
}) {
  return (
    <Card className="border-[color:var(--border-subtle)] bg-[color:var(--surface-0)]">
      <CardContent className="py-4">
        <div className="flex items-center justify-between">
          <div className="space-y-1">
            <p className="text-xs font-medium uppercase tracking-wider text-[var(--muted-foreground)]">
              {label}
            </p>
            <p className="text-2xl font-semibold tracking-tight">{value}</p>
            {subtitle && (
              <p className="text-xs text-[var(--muted-foreground)]">{subtitle}</p>
            )}
          </div>
          <div className="flex size-10 items-center justify-center rounded-md bg-[color:var(--surface-2)]">
            <Icon className="size-5 text-[var(--muted-foreground)]" />
          </div>
        </div>
      </CardContent>
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Tooltip styles (shared)
// ---------------------------------------------------------------------------

const tooltipStyle = {
  backgroundColor: 'var(--surface-2, #1e1e1e)',
  border: '1px solid var(--border-subtle, #333)',
  borderRadius: '6px',
  fontSize: '12px',
  color: 'var(--foreground, #e5e5e5)',
};

// ---------------------------------------------------------------------------
// Backend Comparison Table
// ---------------------------------------------------------------------------

function BackendTable({ data }: { data: BackendStats[] }) {
  if (data.length === 0) {
    return (
      <div
        className="flex h-48 items-center justify-center text-sm text-[var(--muted-foreground)]"
        role="status"
        aria-label="No backend performance data available"
      >
        No backend data available yet. Run some sessions to see metrics here.
      </div>
    );
  }

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-[color:var(--border-subtle)] text-xs uppercase tracking-wider text-[var(--muted-foreground)]">
            <th className="pb-3 pr-4 font-medium">Backend</th>
            <th className="pb-3 pr-4 text-right font-medium">Sessions</th>
            <th className="pb-3 pr-4 text-right font-medium">Success</th>
            <th className="pb-3 pr-4 text-right font-medium">Avg Duration</th>
            <th className="pb-3 text-right font-medium">Retry Rate</th>
          </tr>
        </thead>
        <tbody>
          {data.map((row) => (
            <tr
              key={row.agent_backend}
              className="border-b border-[color:var(--border-subtle)] last:border-0"
            >
              <td className="py-3 pr-4">
                <span className="font-code text-xs">{row.agent_backend}</span>
              </td>
              <td className="py-3 pr-4 text-right tabular-nums">{row.count}</td>
              <td className="py-3 pr-4 text-right">
                <Badge
                  variant={row.success_rate >= 0.8 ? 'default' : row.success_rate >= 0.5 ? 'secondary' : 'destructive'}
                  className="tabular-nums"
                >
                  {formatPercentage(row.success_rate)}
                </Badge>
              </td>
              <td className="py-3 pr-4 text-right tabular-nums">
                {formatDuration(row.avg_duration_seconds)}
              </td>
              <td className="py-3 text-right tabular-nums">
                {formatPercentage(row.retry_rate)}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Success Rate Bar Chart
// ---------------------------------------------------------------------------

function SuccessRateChart({ data }: { data: BackendStats[] }) {
  if (data.length === 0) return null;

  const chartData = useMemo(
    () =>
      data.map((d) => ({
        name: d.agent_backend,
        success: +(d.success_rate * 100).toFixed(1),
        failure: +((1 - d.success_rate) * 100).toFixed(1),
      })),
    [data]
  );

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={chartData} layout="vertical" margin={{ left: 8, right: 16, top: 8, bottom: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle, #333)" horizontal={false} />
        <XAxis type="number" domain={[0, 100]} tick={{ fontSize: 11 }} stroke="var(--muted-foreground)" />
        <YAxis
          type="category"
          dataKey="name"
          width={120}
          tick={{ fontSize: 11, fontFamily: 'var(--font-code)' }}
          stroke="var(--muted-foreground)"
        />
        <Tooltip contentStyle={tooltipStyle} formatter={(v: ValueType | undefined) => `${v ?? 0}%`} />
        <Bar dataKey="success" name="Success" stackId="a" fill={CHART_COLORS.completed} radius={[0, 0, 0, 0]} />
        <Bar dataKey="failure" name="Failure" stackId="a" fill={CHART_COLORS.failed} radius={[0, 4, 4, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------------------
// Session Timeline Chart (stacked bars)
// ---------------------------------------------------------------------------

function SessionTimelineChart({ data }: { data: SessionTimelineEntry[] }) {
  if (data.length === 0) return null;

  const chartData = useMemo(
    () =>
      data.map((d) => ({
        ...d,
        label: shortDate(d.date),
      })),
    [data]
  );

  if (chartData.every((d) => d.total === 0)) {
    return (
      <div
        className="flex h-48 items-center justify-center text-sm text-[var(--muted-foreground)]"
        role="status"
        aria-label="No sessions recorded in this period"
      >
        No sessions recorded in this period.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={chartData} margin={{ left: 8, right: 16, top: 8, bottom: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle, #333)" />
        <XAxis
          dataKey="label"
          tick={{ fontSize: 11 }}
          stroke="var(--muted-foreground)"
          interval="preserveStartEnd"
        />
        <YAxis tick={{ fontSize: 11 }} stroke="var(--muted-foreground)" allowDecimals={false} />
        <Tooltip contentStyle={tooltipStyle} />
        <Bar dataKey="completed" name="Completed" stackId="status" fill={CHART_COLORS.completed} />
        <Bar dataKey="failed" name="Failed" stackId="status" fill={CHART_COLORS.failed} />
        <Bar dataKey="cancelled" name="Cancelled" stackId="status" fill={CHART_COLORS.cancelled} />
        <Bar dataKey="running" name="Running" stackId="status" fill={CHART_COLORS.running} />
        <Bar dataKey="pending" name="Pending" stackId="status" fill={CHART_COLORS.pending} radius={[4, 4, 0, 0]} />
      </BarChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------------------
// Duration by Backend Bar Chart
// ---------------------------------------------------------------------------

function DurationByBackendChart({ data }: { data: BackendStats[] }) {
  const chartData = useMemo(
    () =>
      data
        .filter((d) => d.avg_duration_seconds != null)
        .map((d) => ({ name: d.agent_backend, duration: Math.round(d.avg_duration_seconds!) })),
    [data]
  );

  if (chartData.length === 0) {
    return (
      <div
        className="flex h-48 items-center justify-center text-sm text-[var(--muted-foreground)]"
        role="status"
        aria-label="No duration data available"
      >
        No duration data available yet.
      </div>
    );
  }

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={chartData} margin={{ left: 8, right: 16, top: 8, bottom: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle, #333)" />
        <XAxis
          dataKey="name"
          tick={{ fontSize: 11, fontFamily: 'var(--font-code)' }}
          stroke="var(--muted-foreground)"
          interval={0}
          angle={-35}
          textAnchor="end"
          height={60}
        />
        <YAxis tick={{ fontSize: 11 }} stroke="var(--muted-foreground)" tickFormatter={(v: string | number) => `${v}s`} />
        <Tooltip contentStyle={tooltipStyle} formatter={(v: ValueType | undefined) => formatDuration(Number(v))} />
        <Bar dataKey="duration" name="Avg Duration" radius={[4, 4, 0, 0]}>
          {chartData.map((_, i) => (
            <Cell key={i} fill={BACKEND_PALETTE[i % BACKEND_PALETTE.length]} />
          ))}
        </Bar>
      </BarChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------------------
// Glossary dialog
// ---------------------------------------------------------------------------

const GLOSSARY_ITEMS = [
  {
    term: 'Success vs Failure',
    definition: 'A session is "successful" if the agent completed its work and moved the task to the Review stage. A session "fails" if the agent encountered an error, timed out, or was unable to proceed. Failed sessions may be retried automatically or manually.',
  },
  {
    term: 'Completed',
    definition: 'Task successfully finished—the agent completed work and the task moved to Review for approval.',
  },
  {
    term: 'Failed',
    definition: 'Agent encountered an error, timed out, or could not proceed. Failed sessions can trigger retries.',
  },
  {
    term: 'Cancelled',
    definition: 'Session was manually stopped or interrupted by the user before completion.',
  },
  {
    term: 'Running & Pending',
    definition: 'Running: agent is actively processing. Pending: session is queued or waiting to start.',
  },
  {
    term: 'Total Sessions',
    definition: 'Total number of agent runs initiated across all backends in the selected period.',
  },
  {
    term: 'Avg Success Rate',
    definition: 'Percentage of all sessions completed successfully, weighted by session count per backend. Green badge (≥80%): excellent, Yellow (50-79%): acceptable, Red (<50%): needs improvement.',
  },
  {
    term: 'Avg Duration',
    definition: 'Average time per session, weighted by session count. Useful for identifying slow backends or performance trends.',
  },
  {
    term: 'Success Rate (per backend)',
    definition: 'Percentage of that backend\'s sessions completed successfully. Compare backends to identify the most reliable one.',
  },
  {
    term: 'Retry Rate',
    definition: 'Percentage of sessions that required multiple attempts before completion. High retry rates may indicate unstable backends or challenging tasks.',
  },
  {
    term: 'Active Days',
    definition: 'Number of unique days in the period with at least one session recorded. Useful for understanding usage patterns.',
  },
  {
    term: 'Agent Roles',
    definition: 'WORKER: executes code and implements changes. REVIEWER: analyzes PRs and provides feedback. ORCHESTRATOR: coordinates multi-step workflows.',
  },
  {
    term: 'Task Types',
    definition: 'CODE_IMPLEMENTATION: building new features. BUG_FIX: fixing existing issues. REFACTORING: improving code quality. DOCUMENTATION: adding docs. ARCHITECTURE: design changes. DESIGN: UI/UX design. ANALYSIS: code review or investigation. TESTING: adding tests. DEPLOYMENT: release/infrastructure. INVESTIGATION: debugging. OPTIMIZATION: performance improvements.',
  },
  {
    term: 'Role-Specific Metrics',
    definition: 'Shows success rates and duration for each agent role (worker, reviewer, orchestrator) across different backends, revealing role-specific performance patterns.',
  },
  {
    term: 'Task-Type Metrics',
    definition: 'Breaks down performance by task classification, helping identify which backends excel at specific types of work (e.g., code implementation vs bug fixes).',
  },
];

function GlossaryDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (open: boolean) => void }) {
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-w-md">
        <DialogHeader>
          <DialogTitle>Analytics Glossary</DialogTitle>
        </DialogHeader>
        <div className="space-y-4">
          {GLOSSARY_ITEMS.map((item) => (
            <div key={item.term}>
              <dt className="font-medium text-sm">{item.term}</dt>
              <dd className="text-xs text-[var(--muted-foreground)] mt-1">{item.definition}</dd>
            </div>
          ))}
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// By-Role Analytics
// ---------------------------------------------------------------------------

function RoleCards({ data }: { data: RoleStats[] }) {
  if (data.length === 0) {
    return (
      <div
        className="flex h-32 items-center justify-center text-sm text-[var(--muted-foreground)]"
        role="status"
        aria-label="No role-specific data available"
      >
        No role-specific data available yet.
      </div>
    );
  }

  const roleNames = ['WORKER', 'REVIEWER', 'ORCHESTRATOR'];
  const roleData = roleNames.map((role) => {
    const items = data.filter((d) => d.agent_role === role);
    const totalCount = items.reduce((sum, item) => sum + item.count, 0);
    const weightedSuccess = items.length > 0
      ? items.reduce((sum, item) => sum + item.success_rate * item.count, 0) / totalCount
      : 0;
    const weightedDuration = items.filter((d) => d.avg_duration_seconds !== null).length > 0
      ? items.reduce((sum, item) => sum + (item.avg_duration_seconds ?? 0) * item.count, 0) /
        items.filter((d) => d.avg_duration_seconds !== null).reduce((sum, item) => sum + item.count, 0)
      : null;
    return { role, count: totalCount, success_rate: weightedSuccess, avg_duration_seconds: weightedDuration };
  }).filter(item => item.count > 0);

  if (roleData.length === 0) {
    return (
      <div
        className="flex h-32 items-center justify-center text-sm text-[var(--muted-foreground)]"
        role="status"
      >
        No sessions recorded for any role.
      </div>
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-3">
      {roleData.map((role) => (
        <Card key={role.role} className="border-[color:var(--border-subtle)] bg-[color:var(--surface-0)]">
          <CardContent className="py-4">
            <div className="space-y-3">
              <p className="text-xs font-medium uppercase tracking-wider text-[var(--muted-foreground)]">
                {role.role}
              </p>
              <div className="space-y-1">
                <p className="text-2xl font-semibold">{formatPercentage(role.success_rate)}</p>
                <p className="text-xs text-[var(--muted-foreground)]">Success Rate</p>
              </div>
              <div className="flex items-center justify-between text-xs">
                <span className="text-[var(--muted-foreground)]">{role.count} sessions</span>
                {role.avg_duration_seconds !== null && (
                  <span className="text-[var(--muted-foreground)]">{formatDuration(role.avg_duration_seconds)}</span>
                )}
              </div>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function RoleComparisonChart({ data }: { data: RoleStats[] }) {
  if (data.length === 0) return null;

  const roleNames = ['WORKER', 'REVIEWER', 'ORCHESTRATOR'];
  const backends = Array.from(new Set(data.map((d) => d.agent_backend)));

  const chartData = backends.map((backend) => {
    const item: Record<string, any> = { name: backend };
    roleNames.forEach((role) => {
      const found = data.find((d) => d.agent_backend === backend && d.agent_role === role);
      item[role] = found ? +(found.success_rate * 100).toFixed(1) : 0;
    });
    return item;
  });

  return (
    <ResponsiveContainer width="100%" height={280}>
      <BarChart data={chartData} margin={{ left: 8, right: 16, top: 8, bottom: 8 }}>
        <CartesianGrid strokeDasharray="3 3" stroke="var(--border-subtle, #333)" />
        <XAxis
          dataKey="name"
          tick={{ fontSize: 11, fontFamily: 'var(--font-code)' }}
          stroke="var(--muted-foreground)"
          interval={0}
          angle={-35}
          textAnchor="end"
          height={60}
        />
        <YAxis tick={{ fontSize: 11 }} stroke="var(--muted-foreground)" domain={[0, 100]} />
        <Tooltip contentStyle={tooltipStyle} formatter={(v: ValueType | undefined) => `${v ?? 0}%`} />
        <Bar dataKey="WORKER" name="Worker" stackId="a" fill="#3b82f6" />
        <Bar dataKey="REVIEWER" name="Reviewer" stackId="a" fill="#8b5cf6" />
        <Bar dataKey="ORCHESTRATOR" name="Orchestrator" stackId="a" fill="#ec4899" />
      </BarChart>
    </ResponsiveContainer>
  );
}

// ---------------------------------------------------------------------------
// By-Task-Type Analytics
// ---------------------------------------------------------------------------

function TaskTypeCards({ data }: { data: TaskTypeStats[] }) {
  if (data.length === 0) {
    return (
      <div
        className="flex h-32 items-center justify-center text-sm text-[var(--muted-foreground)]"
        role="status"
        aria-label="No task-type data available"
      >
        No task-type data available yet.
      </div>
    );
  }

  // Aggregate by task type, show top 8
  const typeNames = [
    'code_implementation', 'bug_fix', 'refactoring', 'documentation',
    'architecture', 'design', 'analysis', 'testing'
  ];

  const typeData = typeNames
    .map((type) => {
      const items = data.filter((d) => d.task_type === type);
      if (items.length === 0) return null;
      const totalCount = items.reduce((sum, item) => sum + item.count, 0);
      const weightedSuccess = items.reduce((sum, item) => sum + item.success_rate * item.count, 0) / totalCount;
      return { type, count: totalCount, success_rate: weightedSuccess };
    })
    .filter((item) => item !== null) as Array<{ type: string; count: number; success_rate: number }>;

  if (typeData.length === 0) {
    return (
      <div
        className="flex h-32 items-center justify-center text-sm text-[var(--muted-foreground)]"
        role="status"
      >
        No sessions recorded for any task type.
      </div>
    );
  }

  return (
    <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
      {typeData.map((item) => (
        <Card key={item.type} className="border-[color:var(--border-subtle)] bg-[color:var(--surface-0)]">
          <CardContent className="py-3">
            <div className="space-y-2">
              <p className="text-xs font-medium uppercase tracking-wider text-[var(--muted-foreground)]">
                {item.type.replace(/_/g, ' ')}
              </p>
              <p className="text-xl font-semibold">{formatPercentage(item.success_rate)}</p>
              <p className="text-xs text-[var(--muted-foreground)]">{item.count} sessions</p>
            </div>
          </CardContent>
        </Card>
      ))}
    </div>
  );
}

function TaskTypeTable({ data }: { data: TaskTypeStats[] }) {
  if (data.length === 0) {
    return (
      <div
        className="flex h-48 items-center justify-center text-sm text-[var(--muted-foreground)]"
        role="status"
      >
        No task-type data available.
      </div>
    );
  }

  const backends = Array.from(new Set(data.map((d) => d.agent_backend)));
  const taskTypes = Array.from(new Set(data.map((d) => d.task_type)));

  return (
    <div className="overflow-x-auto">
      <table className="w-full text-left text-sm">
        <thead>
          <tr className="border-b border-[color:var(--border-subtle)] text-xs uppercase tracking-wider text-[var(--muted-foreground)]">
            <th className="pb-3 pr-4 font-medium">Task Type</th>
            {backends.map((backend) => (
              <th key={backend} className="pb-3 pr-4 text-right font-medium text-xs">
                {backend}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {taskTypes.map((type) => (
            <tr key={type} className="border-b border-[color:var(--border-subtle)] last:border-0">
              <td className="py-3 pr-4 text-xs">
                <span className="font-medium">{type.replace(/_/g, ' ')}</span>
              </td>
              {backends.map((backend) => {
                const found = data.find((d) => d.agent_backend === backend && d.task_type === type);
                return (
                  <td key={backend} className="py-3 pr-4 text-right">
                    {found ? (
                      <Badge
                        variant={found.success_rate >= 0.8 ? 'default' : found.success_rate >= 0.5 ? 'secondary' : 'destructive'}
                        className="tabular-nums text-xs"
                      >
                        {formatPercentage(found.success_rate)}
                      </Badge>
                    ) : (
                      <span className="text-xs text-[var(--muted-foreground)]">—</span>
                    )}
                  </td>
                );
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Loading skeleton
// ---------------------------------------------------------------------------

function AnalyticsSkeleton() {
  return (
    <div className="space-y-6">
      <div className="grid gap-4 sm:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-24 rounded-lg" />
        ))}
      </div>
      <Skeleton className="h-80 rounded-lg" />
      <div className="grid gap-4 lg:grid-cols-2">
        <Skeleton className="h-80 rounded-lg" />
        <Skeleton className="h-80 rounded-lg" />
      </div>
    </div>
  );
}

// ---------------------------------------------------------------------------
// Page component
// ---------------------------------------------------------------------------

export function Component() {
  const [backendStats, setBackendStats] = useState<BackendStats[]>([]);
  const [timeline, setTimeline] = useState<SessionTimelineEntry[]>([]);
  const [roleStats, setRoleStats] = useState<RoleStats[]>([]);
  const [taskTypeStats, setTaskTypeStats] = useState<TaskTypeStats[]>([]);
  const [combinedStats, setCombinedStats] = useState<CombinedStats[]>([]);
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);
  const [glossaryOpen, setGlossaryOpen] = useState(false);

  const fetchData = useCallback(async (range: number) => {
    setLoading(true);
    setError(null);
    try {
      const [stats, tl, roles, taskTypes, combined] = await Promise.all([
        apiClient.getBackendStats(),
        apiClient.getSessionTimeline({ days: range }),
        apiClient.getStatsByRole(),
        apiClient.getStatsByTaskType(),
        apiClient.getCombinedStats(),
      ]);
      setBackendStats(stats);
      setTimeline(tl);
      setRoleStats(roles);
      setTaskTypeStats(taskTypes);
      setCombinedStats(combined);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to load analytics');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData(days);
  }, [days, fetchData]);

  const handleExport = useCallback(async () => {
    setExporting(true);
    try {
      const data = await apiClient.getAnalyticsExport({ days });
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: 'application/json' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = 'kagan-analytics.json';
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }, [days]);

  // Derived KPIs
  const { totalSessions, avgSuccessRate, avgDuration } = useMemo(() => {
    const total = backendStats.reduce((sum, b) => sum + b.count, 0);
    const avgSuccess =
      total > 0 ? backendStats.reduce((sum, b) => sum + b.success_rate * b.count, 0) / total : 0;
    const sessionsWithDur = backendStats
      .filter((b) => b.avg_duration_seconds != null)
      .reduce((sum, b) => sum + b.count, 0);
    const avgDur =
      sessionsWithDur > 0
        ? backendStats.reduce((sum, b) => sum + (b.avg_duration_seconds ?? 0) * b.count, 0) /
          sessionsWithDur
        : null;
    return { totalSessions: total, avgSuccessRate: avgSuccess, avgDuration: avgDur };
  }, [backendStats]);

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col px-4 py-8 sm:px-6">
      {/* Header */}
      <header className="flex items-center justify-between pb-6">
        <div>
          <div className="flex items-center gap-2">
            <h1 className="text-lg font-semibold tracking-tight">Analytics</h1>
            <Button
              variant="ghost"
              size="sm"
              className="h-6 w-6 p-0"
              onClick={() => setGlossaryOpen(true)}
              aria-label="Open analytics glossary"
            >
              <HelpCircle className="size-4 text-[var(--muted-foreground)]" />
            </Button>
          </div>
          <p className="text-sm text-[var(--muted-foreground)]">
            Agent performance &amp; session activity
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="h-8 text-xs"
            disabled={exporting}
            onClick={handleExport}
            aria-label="Export analytics as JSON"
          >
            <Download className="mr-1.5 size-3.5" />
            Export
          </Button>
          <Select value={String(days)} onValueChange={(v) => setDays(Number(v))}>
            <SelectTrigger className="h-8 w-32 text-xs">
              <SelectValue />
            </SelectTrigger>
            <SelectContent>
              <SelectItem value="7">Last 7 days</SelectItem>
              <SelectItem value="14">Last 14 days</SelectItem>
              <SelectItem value="30">Last 30 days</SelectItem>
              <SelectItem value="90">Last 90 days</SelectItem>
            </SelectContent>
          </Select>
        </div>
      </header>

      {error && (
        <div className="mt-3 rounded-md border border-[var(--status-error)] bg-[var(--status-error)]/10 px-4 py-3 text-sm text-[var(--status-error)]">
          {error}
        </div>
      )}

      {loading ? (
        <div className="mt-4">
          <AnalyticsSkeleton />
        </div>
      ) : (
        <div className="mt-4 space-y-6">
          {/* KPI Cards */}
          <div className="grid gap-4 sm:grid-cols-3">
            <KpiCard
              label="Total Sessions"
              value={totalSessions.toLocaleString()}
              icon={Activity}
              subtitle={`Across ${backendStats.length} backend${backendStats.length !== 1 ? 's' : ''}`}
            />
            <KpiCard
              label="Avg Success Rate"
              value={formatPercentage(avgSuccessRate)}
              icon={TrendingUp}
              subtitle="Weighted by session count"
            />
            <KpiCard
              label="Avg Duration"
              value={formatDuration(avgDuration)}
              icon={Clock}
              subtitle="Weighted by session count"
            />
          </div>

          {/* Main tabs for different analytics views */}
          <Tabs defaultValue="backend" className="space-y-4">
            <TabsList className="grid grid-cols-4">
              <TabsTrigger value="backend" className="flex items-center gap-2">
                <BarChart3 className="size-4" />
                Backend
              </TabsTrigger>
              <TabsTrigger value="role" className="flex items-center gap-2">
                <Users className="size-4" />
                By Role
              </TabsTrigger>
              <TabsTrigger value="tasktype" className="flex items-center gap-2">
                <BarChart3 className="size-4" />
                By Type
              </TabsTrigger>
              <TabsTrigger value="combined" className="flex items-center gap-2">
                <Grid3x3 className="size-4" />
                Combined
              </TabsTrigger>
            </TabsList>

            {/* Backend Performance Tab */}
            <TabsContent value="backend" className="space-y-4">
              <Card className="border-[color:var(--border-subtle)] bg-[color:var(--surface-0)]">
                <CardHeader>
                  <CardTitle
                    className="flex items-center gap-2 text-sm"
                    aria-label="Backend performance metrics table and chart"
                  >
                    <BarChart3 className="size-4 text-[var(--muted-foreground)]" />
                    Backend Performance
                  </CardTitle>
                </CardHeader>
                <CardContent>
                  <Tabs defaultValue="table">
                    <TabsList variant="line" className="mb-4">
                      <TabsTrigger value="table">Table</TabsTrigger>
                      <TabsTrigger value="chart">Success Rate</TabsTrigger>
                    </TabsList>
                    <TabsContent value="table">
                      <BackendTable data={backendStats} />
                    </TabsContent>
                    <TabsContent value="chart">
                      <SuccessRateChart data={backendStats} />
                    </TabsContent>
                  </Tabs>
                </CardContent>
              </Card>

              {/* Duration & Timeline side-by-side */}
              <div className="grid gap-4 lg:grid-cols-2">
                <Card className="border-[color:var(--border-subtle)] bg-[color:var(--surface-0)]">
                  <CardHeader>
                    <CardTitle
                      className="flex items-center gap-2 text-sm"
                      aria-label="Average session duration by backend"
                    >
                      <Clock className="size-4 text-[var(--muted-foreground)]" />
                      Duration by Backend
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <DurationByBackendChart data={backendStats} />
                  </CardContent>
                </Card>

                <Card className="border-[color:var(--border-subtle)] bg-[color:var(--surface-0)]">
                  <CardHeader>
                    <CardTitle
                      className="flex items-center gap-2 text-sm"
                      aria-label="Daily session activity over time"
                    >
                      <Activity className="size-4 text-[var(--muted-foreground)]" />
                      Session Activity
                    </CardTitle>
                  </CardHeader>
                  <CardContent>
                    <SessionTimelineChart data={timeline} />
                  </CardContent>
                </Card>
              </div>
            </TabsContent>

            {/* By-Role Tab */}
            <TabsContent value="role" className="space-y-4">
              <Card className="border-[color:var(--border-subtle)] bg-[color:var(--surface-0)]">
                <CardHeader>
                  <CardTitle className="flex items-center gap-2 text-sm">
                    <Users className="size-4 text-[var(--muted-foreground)]" />
                    Performance by Agent Role
                  </CardTitle>
                  <p className="text-xs text-[var(--muted-foreground)] mt-2">
                    Success rate and duration metrics for each agent role across backends.
                  </p>
                </CardHeader>
                <CardContent>
                  <RoleCards data={roleStats} />
                </CardContent>
              </Card>

              <Card className="border-[color:var(--border-subtle)] bg-[color:var(--surface-0)]">
                <CardHeader>
                  <CardTitle className="text-sm">Role Comparison by Backend</CardTitle>
                </CardHeader>
                <CardContent>
                  <RoleComparisonChart data={roleStats} />
                </CardContent>
              </Card>
            </TabsContent>

            {/* By-Task-Type Tab */}
            <TabsContent value="tasktype" className="space-y-4">
              <Card className="border-[color:var(--border-subtle)] bg-[color:var(--surface-0)]">
                <CardHeader>
                  <CardTitle className="text-sm">Performance by Task Type</CardTitle>
                  <p className="text-xs text-[var(--muted-foreground)] mt-2">
                    Success rates for different task classifications. Showing top types by frequency.
                  </p>
                </CardHeader>
                <CardContent>
                  <TaskTypeCards data={taskTypeStats} />
                </CardContent>
              </Card>

              <Card className="border-[color:var(--border-subtle)] bg-[color:var(--surface-0)]">
                <CardHeader>
                  <CardTitle className="text-sm">Backend × Task Type Matrix</CardTitle>
                </CardHeader>
                <CardContent>
                  <TaskTypeTable data={taskTypeStats} />
                </CardContent>
              </Card>
            </TabsContent>

            {/* Combined Tab */}
            <TabsContent value="combined" className="space-y-4">
              <Card className="border-[color:var(--border-subtle)] bg-[color:var(--surface-0)]">
                <CardHeader>
                  <CardTitle className="text-sm">Combined Analytics (Backend × Role × Task Type)</CardTitle>
                  <p className="text-xs text-[var(--muted-foreground)] mt-2">
                    Three-dimensional breakdown showing how each backend performs across all roles and task types.
                  </p>
                </CardHeader>
                <CardContent>
                  <div className="overflow-x-auto">
                    <table className="w-full text-left text-xs">
                      <thead>
                        <tr className="border-b border-[color:var(--border-subtle)]">
                          <th className="pb-2 pr-4 font-medium">Backend</th>
                          <th className="pb-2 pr-4 font-medium">Role</th>
                          <th className="pb-2 pr-4 font-medium">Task Type</th>
                          <th className="pb-2 pr-4 text-right font-medium">Sessions</th>
                          <th className="pb-2 pr-4 text-right font-medium">Success</th>
                          <th className="pb-2 text-right font-medium">Avg Duration</th>
                        </tr>
                      </thead>
                      <tbody>
                        {combinedStats.length === 0 ? (
                          <tr>
                            <td colSpan={6} className="py-4 text-center text-[var(--muted-foreground)]">
                              No combined data available.
                            </td>
                          </tr>
                        ) : (
                          combinedStats.slice(0, 50).map((row, idx) => (
                            <tr key={idx} className="border-b border-[color:var(--border-subtle)] last:border-0">
                              <td className="py-2 pr-4 font-code">{row.agent_backend}</td>
                              <td className="py-2 pr-4">{row.agent_role}</td>
                              <td className="py-2 pr-4">{row.task_type.replace(/_/g, ' ')}</td>
                              <td className="py-2 pr-4 text-right tabular-nums">{row.count}</td>
                              <td className="py-2 pr-4 text-right">
                                <Badge
                                  variant={row.success_rate >= 0.8 ? 'default' : row.success_rate >= 0.5 ? 'secondary' : 'destructive'}
                                  className="text-xs tabular-nums"
                                >
                                  {formatPercentage(row.success_rate)}
                                </Badge>
                              </td>
                              <td className="py-2 text-right tabular-nums">
                                {row.avg_duration_seconds !== null ? formatDuration(row.avg_duration_seconds) : '—'}
                              </td>
                            </tr>
                          ))
                        )}
                      </tbody>
                    </table>
                  </div>
                  {combinedStats.length > 50 && (
                    <p className="mt-2 text-xs text-[var(--muted-foreground)]">
                      Showing first 50 of {combinedStats.length} entries. Use filters or export for full data.
                    </p>
                  )}
                </CardContent>
              </Card>
            </TabsContent>
          </Tabs>
        </div>
      )}

      <GlossaryDialog open={glossaryOpen} onOpenChange={setGlossaryOpen} />
    </div>
  );
}
