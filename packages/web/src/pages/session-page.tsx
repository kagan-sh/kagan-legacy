import { useCallback, useEffect, useMemo, useState } from 'react';
import { useParams, useNavigate, useSearchParams } from 'react-router';
import { useSetAtom } from 'jotai';
import { ArrowLeft } from 'lucide-react';
import { AgentControl } from '@/components/board/agent-control';
import { DiffViewer } from '@/components/board/diff-viewer';
import { ReviewPanel } from '@/components/board/review-panel';
import { TaskMetadataPanel } from '@/components/board/task-metadata-panel';
import { EventStream } from '@/components/session/event-stream';
import { FollowUpQueue } from '@/components/session/follow-up-queue';
import { TaskCommitsPanel } from '@/components/session/task-commits-panel';
import { ChatInputBar } from '@/components/chat/chat-input-bar';
import { Button } from '@/components/ui/button';
import { ResizableHandle, ResizablePanel, ResizablePanelGroup } from '@/components/ui/resizable';
import { Tabs, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { apiClient } from '@/lib/api/client';
import type { TaskCommitsResponse, TaskStatus, TaskWorktreeResponse, WireTaskSession } from '@/lib/api/types';
import { useTaskEvents } from '@/lib/hooks/use-task-events';
import { Panel } from '@/components/shared/workspace';
import { ErrorBoundary } from '@/components/shared/error-boundary';
import { rightRailChatSessionIdAtom, rightRailModeAtom, rightRailTaskIdAtom } from '@/lib/atoms/ui';
import { STATUS_LABELS } from '@/lib/utils/constants';

export function Component() {
  const { taskId } = useParams<{ taskId: string }>();
  const navigate = useNavigate();
  const [searchParams, setSearchParams] = useSearchParams();
  const [worktree, setWorktree] = useState<TaskWorktreeResponse['worktree'] | null>(null);
  const [commits, setCommits] = useState<TaskCommitsResponse | null>(null);
  const [commitsLoading, setCommitsLoading] = useState(false);
  const [commitsError, setCommitsError] = useState<string | null>(null);
  const [worktreePath, setWorktreePath] = useState<string | null>(null);
  const [pairLauncher, setPairLauncher] = useState<string | null>(null);

  const requestedLane = searchParams.get('lane');

  // Pre-fetch sessions so we can scope the event fetch to the correct lane
  const [sessionsPreload, setSessionsPreload] = useState<WireTaskSession[]>([]);
  useEffect(() => {
    if (!taskId) return;
    void apiClient.getTaskSessions(taskId).then(setSessionsPreload).catch(() => undefined);
  }, [taskId]);

  const workerSession = useMemo(
    () => sessionsPreload.find((s) => s.mode === 'AUTO' || s.mode === 'PAIR'),
    [sessionsPreload],
  );
  const reviewerSession = useMemo(
    () => (sessionsPreload.length >= 2 ? sessionsPreload[sessionsPreload.length - 1] : undefined),
    [sessionsPreload],
  );
  const hasReviewerSession = reviewerSession !== undefined;

  const streamLane =
    requestedLane === 'reviewer' || requestedLane === 'worker'
      ? requestedLane
      : reviewerSession
        ? 'reviewer'
        : 'worker';

  const laneSessionId = streamLane === 'reviewer' ? reviewerSession?.id : workerSession?.id;

  const {
    task, events, loading, runningSince, isRunning, sessions,
    sentFollowUps, queue, sendingFollowUp,
    queuePrompt, removePrompt, editPrompt, interruptAndSend,
    hasMore, loadingMore, loadEarlier,
  } = useTaskEvents(taskId, { sessionId: laneSessionId });

  useEffect(() => {
    if (sessions && sessions.length > 0) setSessionsPreload(sessions);
  }, [sessions]);

  // Keep rail task ID in sync so Cmd+L opens chat for this task
  const setRailMode = useSetAtom(rightRailModeAtom);
  const setRailTaskId = useSetAtom(rightRailTaskIdAtom);
  const setRailChatSessionId = useSetAtom(rightRailChatSessionIdAtom);
  useEffect(() => {
    if (taskId) {
      setRailTaskId(taskId);
      setRailChatSessionId(null);
    }
    return () => setRailTaskId(null);
  }, [setRailChatSessionId, setRailTaskId, taskId]);

  const updateLane = useCallback(
    (lane: 'worker' | 'reviewer') => {
      const nextParams = new URLSearchParams(searchParams);
      nextParams.set('lane', lane);
      setSearchParams(nextParams, { replace: true });
    },
    [searchParams, setSearchParams],
  );

  const displayTask = task;
  const hasWorkspace = Boolean(displayTask?.has_workspace);
  const isCommitsPanelLoading =
    hasWorkspace && !commitsError && (commitsLoading || commits === null);
  const hasCommitWorkspace =
    hasWorkspace &&
    (isCommitsPanelLoading || Boolean(worktree?.path) || Boolean(commits?.branch));

  useEffect(() => {
    if (!taskId || displayTask?.execution_mode !== 'PAIR') {
      setWorktreePath(null);
      setPairLauncher(null);
      return;
    }

    let cancelled = false;

    void apiClient.getTaskWorktree(taskId).then(
      (res) => {
        if (!cancelled) {
          setWorktreePath(res.worktree?.path ?? null);
        }
      },
      () => {
        if (!cancelled) {
          setWorktreePath(null);
        }
      },
    );

    void apiClient.getSettings().then(
      (settings) => {
        if (!cancelled) {
          setPairLauncher(settings.pair_launcher ?? null);
        }
      },
      () => {
        if (!cancelled) {
          setPairLauncher(null);
        }
      },
    );

    return () => {
      cancelled = true;
    };
  }, [taskId, displayTask?.execution_mode]);

  useEffect(() => {
    if (!taskId || !hasWorkspace) {
      setWorktree(null);
      setCommits(null);
      setCommitsLoading(false);
      setCommitsError(null);
      return;
    }

    let cancelled = false;
    setCommitsLoading(true);
    setCommitsError(null);

    void Promise.all([
      apiClient.getTaskWorktree(taskId),
      apiClient.getTaskCommits(taskId),
    ])
      .then(([worktreeResponse, commitsResponse]) => {
        if (!cancelled) {
          setWorktree(worktreeResponse.worktree);
          setCommits(commitsResponse);
        }
      })
      .catch((error) => {
        if (!cancelled) {
          setWorktree(null);
          setCommits(null);
          setCommitsError(error instanceof Error ? error.message : 'Commit history unavailable');
        }
      })
      .finally(() => {
        if (!cancelled) {
          setCommitsLoading(false);
        }
      });

    return () => {
      cancelled = true;
    };
  }, [hasWorkspace, taskId]);

  if (loading && !displayTask) {
    return (
      <div className="flex h-full items-center justify-center px-6 py-10">
        <div className="h-14 w-56 animate-pulse bg-[var(--muted)]" />
      </div>
    );
  }

  if (!displayTask) {
    return (
      <div className="flex h-full items-center justify-center px-6 py-10 text-sm text-[var(--muted-foreground)]">
        Task not found
      </div>
    );
  }

  return (
    <ErrorBoundary level="feature">
    <div className="mx-auto flex h-full w-full max-w-[1680px] min-h-0 flex-col px-4 py-3 sm:px-6">
      <div className="flex items-center gap-2 border-b border-[color:var(--border-subtle)] pb-3">
        <Button variant="ghost" size="icon-sm" onClick={() => navigate(-1)} aria-label="Go back">
          <ArrowLeft className="size-4" />
        </Button>
        <h1 className="truncate text-sm font-semibold">{displayTask.title}</h1>
        <span className="h-4 w-px bg-[color:var(--border-subtle)]" />
        <span className="text-xs text-[var(--muted-foreground)]">Session</span>
        {(displayTask.active_session?.agent_backend ?? displayTask.agent_backend) ? (
          <span className="rounded bg-[var(--muted)] px-1.5 py-0.5 font-code text-[10px] text-[var(--muted-foreground)]">
            {displayTask.active_session?.agent_backend ?? displayTask.agent_backend}
          </span>
        ) : null}
        <div className="ml-auto flex items-center gap-2">
          <Button
            variant="secondary"
            size="sm"
            onClick={() => {
              setRailTaskId(displayTask.id);
              setRailChatSessionId(null);
              setRailMode('chat-right');
            }}
          >
            Open chat
          </Button>
        </div>
      </div>

      <Panel className="mt-3 flex min-h-0 flex-1 flex-col overflow-hidden">
        <div className="grid min-h-0 flex-1 gap-5 p-5 xl:grid-cols-[minmax(0,1fr)_20rem]">
          <div className="min-h-0">
            {hasWorkspace ? (
              <ResizablePanelGroup orientation="vertical" className="min-h-0 gap-4">
                <ResizablePanel defaultSize={58} minSize={36}>
                  <div className="flex h-full min-h-0 flex-col gap-4">
                    <Tabs value={streamLane} onValueChange={(v) => updateLane(v as 'worker' | 'reviewer')}>
                      <TabsList>
                        <TabsTrigger value="worker">Worker</TabsTrigger>
                        <TabsTrigger value="reviewer" disabled={!hasReviewerSession}>Reviewer</TabsTrigger>
                      </TabsList>
                    </Tabs>

                    <div className="flex min-h-0 flex-1 flex-col">
                      <EventStream events={events} userFollowUps={sentFollowUps} isRunning={isRunning} className="min-h-0 flex-1" hasMore={hasMore} loadingMore={loadingMore} onLoadEarlier={loadEarlier} />
                      <ChatInputBar
                        onSend={queuePrompt}
                        disableSend={false}
                        placeholder={`Queue a follow-up for the ${streamLane} agent...`}
                      />
                    </div>
                  </div>
                </ResizablePanel>
                <ResizableHandle withHandle />
                <ResizablePanel defaultSize={42} minSize={24}>
                  <Panel className="flex h-full min-h-0 flex-col overflow-hidden">
                    <div className="flex items-center gap-2 border-b border-[color:var(--border-subtle)] px-4 py-2.5">
                      <h2 className="text-xs font-semibold">Workspace Changes</h2>
                      <span className="text-[10px] text-[var(--muted-foreground)]">File diffs from task worktree</span>
                    </div>
                    <div className="min-h-0 flex-1 px-5 pb-5">
                      <DiffViewer taskId={displayTask.id} taskStatus={displayTask.status} className="h-full" />
                    </div>
                  </Panel>
                </ResizablePanel>
              </ResizablePanelGroup>
            ) : (
              <div className="flex min-h-0 flex-col gap-4">
                <Tabs value={streamLane} onValueChange={(v) => updateLane(v as 'worker' | 'reviewer')}>
                  <TabsList>
                    <TabsTrigger value="worker">Worker</TabsTrigger>
                    <TabsTrigger value="reviewer" disabled={!hasReviewerSession}>Reviewer</TabsTrigger>
                  </TabsList>
                </Tabs>

                <div className="flex min-h-0 flex-1 flex-col">
                  <EventStream events={events} userFollowUps={sentFollowUps} isRunning={isRunning} className="min-h-0 flex-1" hasMore={hasMore} loadingMore={loadingMore} onLoadEarlier={loadEarlier} />
                  <ChatInputBar
                    onSend={queuePrompt}
                    disableSend={false}
                    placeholder={`Queue a follow-up for the ${streamLane} agent...`}
                  />
                </div>
              </div>
            )}
          </div>

          <div className="min-h-0 space-y-4 overflow-y-auto pr-1">
            <AgentControl
              taskId={displayTask.id}
              status={displayTask.status}
              executionMode={displayTask.execution_mode}
              startedAt={runningSince}
              worktreePath={worktreePath}
              pairLauncher={pairLauncher}
              taskLauncher={displayTask.launcher}
            />

            <TaskMetadataPanel
              task={displayTask}
              runtimeTitle="Workspace Context"
              showTaskDataSection={false}
              runtimeRows={[
                {
                  label: 'Workflow',
                  value: STATUS_LABELS[displayTask.status as TaskStatus] ?? displayTask.status,
                },
                {
                  label: 'Lane',
                  value: streamLane === 'reviewer' ? 'Reviewer' : 'Worker',
                },
                {
                  label: 'Workspace',
                  value: hasWorkspace ? 'Provisioned' : 'Not provisioned',
                },
                {
                  label: 'Branch',
                  value: worktree?.branch || displayTask.base_branch || 'Project default',
                },
                {
                  label: 'Worktree',
                  value: worktree?.path || 'No active worktree path',
                  rowClassName: 'flex items-start justify-between gap-2',
                  valueClassName: 'max-w-[12rem] text-right text-xs leading-5 text-[var(--muted-foreground)]',
                },
              ]}
            />

            <TaskCommitsPanel
              commits={commits?.commits ?? []}
              branch={commits?.branch ?? worktree?.branch ?? null}
              baseBranch={commits?.base_branch ?? displayTask.base_branch ?? 'main'}
              hasWorkspace={hasCommitWorkspace}
              loading={isCommitsPanelLoading}
              error={commitsError}
            />

            <FollowUpQueue
              prompts={queue}
              sending={sendingFollowUp}
              agentRunning={isRunning}
              onRemove={removePrompt}
              onEdit={editPrompt}
              onInterruptAndSend={interruptAndSend}
            />

            {displayTask.status === 'REVIEW' ? (
              <ReviewPanel taskId={displayTask.id} />
            ) : null}
          </div>
        </div>
      </Panel>
    </div>
    </ErrorBoundary>
  );
}
