import { useCallback, useEffect, useState } from 'react';
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
  TrendingUp,
} from 'lucide-react';
import { apiClient } from '@/lib/api/client';
import type { BackendStats, SessionTimelineEntry } from '@/lib/api/types';
import { Button } from '@/components/ui/button';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
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

function formatDuration(seconds: number | null | undefined): string {
  if (seconds == null) return '--';
  if (seconds < 60) return `${Math.round(seconds)}s`;
  const mins = Math.floor(seconds / 60);
  const secs = Math.round(seconds % 60);
  return secs > 0 ? `${mins}m ${secs}s` : `${mins}m`;
}

function formatPct(v: number): string {
  return `${(v * 100).toFixed(1)}%`;
}

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
      <div className="flex h-48 items-center justify-center text-sm text-[var(--muted-foreground)]">
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
                  {formatPct(row.success_rate)}
                </Badge>
              </td>
              <td className="py-3 pr-4 text-right tabular-nums">
                {formatDuration(row.avg_duration_seconds)}
              </td>
              <td className="py-3 text-right tabular-nums">
                {formatPct(row.retry_rate)}
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

  const chartData = data.map((d) => ({
    name: d.agent_backend,
    success: +(d.success_rate * 100).toFixed(1),
    failure: +((1 - d.success_rate) * 100).toFixed(1),
  }));

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

  const chartData = data.map((d) => ({
    ...d,
    label: shortDate(d.date),
  }));

  if (chartData.every((d) => d.total === 0)) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-[var(--muted-foreground)]">
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
  const chartData = data
    .filter((d) => d.avg_duration_seconds != null)
    .map((d) => ({ name: d.agent_backend, duration: Math.round(d.avg_duration_seconds!) }));

  if (chartData.length === 0) {
    return (
      <div className="flex h-48 items-center justify-center text-sm text-[var(--muted-foreground)]">
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
  const [days, setDays] = useState(30);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  const fetchData = useCallback(async (range: number) => {
    setLoading(true);
    setError(null);
    try {
      const [stats, tl] = await Promise.all([
        apiClient.getBackendStats(),
        apiClient.getSessionTimeline({ days: range }),
      ]);
      setBackendStats(stats);
      setTimeline(tl);
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
  const totalSessions = backendStats.reduce((sum, b) => sum + b.count, 0);
  const avgSuccessRate =
    totalSessions > 0
      ? backendStats.reduce((sum, b) => sum + b.success_rate * b.count, 0) / totalSessions
      : 0;
  const avgDuration =
    backendStats.filter((b) => b.avg_duration_seconds != null).length > 0
      ? backendStats.reduce((sum, b) => sum + (b.avg_duration_seconds ?? 0) * b.count, 0) / totalSessions
      : null;

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col px-4 py-8 sm:px-6">
      {/* Header */}
      <div className="flex items-center justify-between pb-6">
        <div>
          <h1 className="text-lg font-semibold tracking-tight">Analytics</h1>
          <p className="text-sm text-[var(--muted-foreground)]">
            Agent performance &amp; session activity
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="outline"
            size="sm"
            className="h-8 text-xs"
            disabled={loading || exporting}
            onClick={handleExport}
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
      </div>

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
              value={formatPct(avgSuccessRate)}
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

          {/* Backend comparison */}
          <Card className="border-[color:var(--border-subtle)] bg-[color:var(--surface-0)]">
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-sm">
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
                <CardTitle className="flex items-center gap-2 text-sm">
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
                <CardTitle className="flex items-center gap-2 text-sm">
                  <Activity className="size-4 text-[var(--muted-foreground)]" />
                  Session Activity
                </CardTitle>
              </CardHeader>
              <CardContent>
                <SessionTimelineChart data={timeline} />
              </CardContent>
            </Card>
          </div>
        </div>
      )}
    </div>
  );
}
