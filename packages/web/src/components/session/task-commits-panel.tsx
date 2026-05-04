import { ArrowRight, GitBranch, GitCommitHorizontal } from 'lucide-react';
import type { ReactNode } from 'react';
import { InspectorSection } from '@/components/shared/workspace';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import type { TaskCommit } from '@kagan/shared-api-client';

const MAX_VISIBLE_COMMITS = 8;

interface TaskCommitsPanelProps {
  commits: TaskCommit[];
  branch?: string | null;
  baseBranch?: string | null;
  hasWorkspace: boolean;
  loading?: boolean;
  error?: string | null;
  className?: string;
}

export function TaskCommitsPanel({
  commits,
  branch,
  baseBranch,
  hasWorkspace,
  loading = false,
  error = null,
  className,
}: TaskCommitsPanelProps) {
  const resolvedBaseBranch = baseBranch?.trim() || 'main';
  const resolvedBranch = branch?.trim() || null;
  const visibleCommits = commits.slice(0, MAX_VISIBLE_COMMITS);
  const remainingCommits = Math.max(0, commits.length - visibleCommits.length);

  return (
    <InspectorSection
      title="Commits"
      className={className}
      action={(
        <div className="hidden items-center gap-2 sm:flex">
          {resolvedBranch ? (
            <>
              <Badge
                variant="outline"
                className="gap-1.5 border-[color:var(--border-subtle)] bg-[color:var(--surface-0)] px-2.5 py-1 font-code text-[10px] tracking-[0.16em]"
              >
                <GitBranch className="size-3" />
                {resolvedBranch}
              </Badge>
              <ArrowRight className="size-3.5 text-[var(--muted-foreground)]" />
            </>
          ) : null}
          <Badge
            variant="outline"
            className=" border-[color:var(--border-subtle)] bg-[color:var(--surface-0)] px-2.5 py-1 font-code text-[10px] tracking-[0.16em]"
          >
            {resolvedBaseBranch}
          </Badge>
        </div>
      )}
    >
      {loading ? (
        <div className="space-y-3">
          <div className="inline-flex items-center gap-2 text-xs text-[var(--muted-foreground)]">
            <GitCommitHorizontal className="size-4 text-[var(--primary)]" />
            Loading commits...
          </div>
          <div className="space-y-2">
            {Array.from({ length: 3 }, (_, index) => (
              <div
                key={`task-commit-skeleton-${index}`}
                className=" border border-[color:var(--border-subtle)] bg-[color:var(--surface-0)]/70 px-3 py-3"
              >
                <Skeleton className="h-4 w-20 " />
                <Skeleton className="mt-3 h-4 w-full max-w-[18rem]" />
              </div>
            ))}
          </div>
        </div>
      ) : error ? (
        <CommitState
          title="Commit history unavailable"
          description={error}
          icon={<GitCommitHorizontal className="size-4 text-[var(--primary)]" />}
        />
      ) : !hasWorkspace ? (
        <CommitState
          title="No workspace yet"
          description="Start or open a task session to materialize the branch before commit history can appear."
          icon={<GitBranch className="size-4 text-[var(--primary)]" />}
        />
      ) : visibleCommits.length === 0 ? (
        <CommitState
          title="No task-branch commits"
          description={`This branch has not moved ahead of ${resolvedBaseBranch} yet.`}
          icon={<GitCommitHorizontal className="size-4 text-[var(--primary)]" />}
        />
      ) : (
        <div className="space-y-3">
          <div className="flex items-center justify-between gap-3 text-xs text-[var(--muted-foreground)]">
            <span>
              {commits.length} {commits.length === 1 ? 'commit' : 'commits'} ahead of{' '}
              {resolvedBaseBranch}
            </span>
            {remainingCommits > 0 ? <span>Latest {visibleCommits.length} shown</span> : null}
          </div>

          <ol className="space-y-2">
            {visibleCommits.map((commit) => (
              <li
                key={`${commit.short_hash}-${commit.message}`}
                className=" border border-[color:var(--border-subtle)] bg-[color:var(--surface-0)]/80 px-3 py-2.5 shadow-[var(--soft-shadow)]"
              >
                <div className="flex items-start gap-3">
                  <span className="inline-flex shrink-0 bg-[color:var(--surface-2)] px-2.5 py-1 font-code text-[10px] tracking-[0.16em] text-[var(--foreground)]">
                    {commit.short_hash}
                  </span>
                  <p className="min-w-0 flex-1 break-words text-sm leading-6 text-[var(--foreground)]">
                    {commit.message}
                  </p>
                </div>
              </li>
            ))}
          </ol>

          {remainingCommits > 0 ? (
            <div className=" border border-dashed border-[color:var(--border-subtle)] bg-[color:var(--surface-0)]/50 px-3 py-2 text-xs text-[var(--muted-foreground)]">
              +{remainingCommits} more {remainingCommits === 1 ? 'commit' : 'commits'}
            </div>
          ) : null}
        </div>
      )}
    </InspectorSection>
  );
}

function CommitState({
  title,
  description,
  icon,
}: {
  title: string;
  description: string;
  icon: ReactNode;
}) {
  return (
    <div className=" border border-dashed border-[color:var(--border-subtle)] bg-[color:var(--surface-0)]/60 px-4 py-4">
      <div className="mb-2 inline-flex items-center gap-2 text-sm font-medium text-[var(--foreground)]">
        {icon}
        {title}
      </div>
      <p className="text-sm leading-6 text-[var(--muted-foreground)]">{description}</p>
    </div>
  );
}
