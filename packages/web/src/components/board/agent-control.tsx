import { useState, useEffect, useCallback, useMemo } from 'react';
import { Loader2, Play, Square, Clock, Users, ExternalLink, Terminal } from 'lucide-react';
import { useAtomValue } from 'jotai';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api/client';
import { kaganWs, type WsInboundMessage } from '@/lib/api/websocket';
import { wsConnectedAtom } from '@/lib/atoms/connection';
import { cn } from '@/lib/utils';
import { openInEditor, buildEditorLink, launcherDisplayName, type LauncherBackend } from '@/lib/utils/editor-links';
import { Button } from '@/components/ui/button';
interface AgentControlProps {
  taskId: string;
  status: string;
  executionMode?: string;
  startedAt?: string | null;
  buttonSize?: 'xs' | 'sm';
  className?: string;
  worktreePath?: string | null;
  pairLauncher?: string | null;
}

export function AgentControl({
  taskId,
  status,
  executionMode,
  startedAt,
  buttonSize = 'xs',
  className,
  worktreePath,
  pairLauncher,
}: AgentControlProps) {
  const wsConnected = useAtomValue(wsConnectedAtom);
  const isRunning = status === 'IN_PROGRESS';
  const [pending, setPending] = useState<'starting' | 'stopping' | null>(null);
  const [elapsed, setElapsed] = useState(0);
  const [fallbackStartedAtMs, setFallbackStartedAtMs] = useState<number | null>(null);

  const startedAtMs = useMemo(() => {
    if (!startedAt) return null;
    const parsed = Date.parse(startedAt);
    return Number.isNaN(parsed) ? null : parsed;
  }, [startedAt]);
  const effectiveStartedAtMs = startedAtMs ?? fallbackStartedAtMs;

  // Clear pending state when status actually changes
  useEffect(() => {
    setPending(null);
  }, [status]);

  // Listen for WS responses to give immediate feedback
  useEffect(() => {
    const cleanups = [
      kaganWs.on('RUN_STARTED', (data: WsInboundMessage) => {
        if (data.task_id === taskId) setPending(null);
      }),
      kaganWs.on('RUN_CANCELLED', (data: WsInboundMessage) => {
        if (data.task_id === taskId) setPending(null);
      }),
      kaganWs.on('RUN_ERROR', (data: WsInboundMessage) => {
        if (data.task_id === taskId) {
          setPending(null);
          toast.error(typeof data.error === 'string' ? data.error : 'Agent run failed');
        }
      }),
    ];
    return () => cleanups.forEach((fn) => fn());
  }, [taskId]);

  // Elapsed timer
  const computeElapsed = useCallback(() => {
    if (!isRunning || effectiveStartedAtMs === null) return 0;
    return Math.max(0, Math.floor((Date.now() - effectiveStartedAtMs) / 1000));
  }, [isRunning, effectiveStartedAtMs]);

  useEffect(() => {
    if (!isRunning) {
      setFallbackStartedAtMs(null);
      return;
    }
    if (startedAtMs === null && fallbackStartedAtMs === null) {
      setFallbackStartedAtMs(Date.now());
    }
  }, [isRunning, startedAtMs, fallbackStartedAtMs]);

  useEffect(() => {
    if (!isRunning || effectiveStartedAtMs === null) {
      setElapsed(0);
      return;
    }
    setElapsed(computeElapsed());
    const interval = setInterval(() => setElapsed(computeElapsed()), 1000);
    return () => clearInterval(interval);
  }, [isRunning, effectiveStartedAtMs, computeElapsed]);

  const formatTime = (secs: number) => {
    const h = Math.floor(secs / 3600);
    const m = Math.floor((secs % 3600) / 60);
    const s = secs % 60;
    if (h > 0) {
      return `${h}:${String(m).padStart(2, '0')}:${String(s).padStart(2, '0')}`;
    }
    return `${m}:${String(s).padStart(2, '0')}`;
  };

  const isPair = executionMode === 'PAIR';

  const handleStart = useCallback(async () => {
    setPending('starting');
    if (isPair) {
      try {
        await apiClient.pairTask(taskId);
        if (worktreePath) {
          const launcher = (pairLauncher || 'vscode') as LauncherBackend;
          const opened = openInEditor(launcher, worktreePath);
          if (opened) {
            toast.success(`Opening ${launcherDisplayName(launcher)}...`);
          }
        }
      } catch (err) {
        toast.error(err instanceof Error ? err.message : 'Failed to start pair session');
        setPending(null);
      }
    } else {
      kaganWs.startRun(taskId);
    }
  }, [taskId, isPair, worktreePath, pairLauncher]);

  const handleStop = useCallback(async () => {
    setPending('stopping');
    if (isPair) {
      try {
        await apiClient.endPairing(taskId);
      } catch (err) {
        toast.error(err instanceof Error ? err.message : 'Failed to end pair session');
        setPending(null);
      }
    } else {
      kaganWs.cancelRun(taskId);
    }
  }, [taskId, isPair]);

  const isBusy = pending !== null;

  return (
    <div className={cn('flex items-center gap-2', className)}>
      {isRunning || pending === 'starting' ? (
        <>
          <Button
            size={buttonSize}
            onClick={handleStop}
            disabled={!wsConnected || isBusy}
          >
            {pending === 'stopping' ? <Loader2 className="size-3 animate-spin" /> : <Square className="size-3" />}
            {pending === 'stopping' ? 'Stopping...' : 'Stop'}
          </Button>
          {isPair && isRunning && worktreePath && (() => {
            const launcher = (pairLauncher || 'vscode') as LauncherBackend;
            const link = buildEditorLink(launcher, worktreePath);

            if (link.supportsDeepLink) {
              return (
                <Button
                  variant="secondary"
                  size={buttonSize}
                  onClick={() => openInEditor(launcher, worktreePath)}
                >
                  <ExternalLink className="size-3" />
                  {link.label}
                </Button>
              );
            }

            return (
              <Button
                variant="secondary"
                size={buttonSize}
                onClick={() => {
                  if (link.fallbackMessage) {
                    navigator.clipboard.writeText(link.fallbackMessage).then(
                      () => toast.info('Terminal command copied to clipboard'),
                      () => toast.info(link.fallbackMessage!),
                    );
                  }
                }}
                title={link.fallbackMessage ?? undefined}
              >
                <Terminal className="size-3" />
                {link.label}
              </Button>
            );
          })()}
          {isRunning && (
            <span className="flex items-center gap-1 text-xs text-[var(--muted-foreground)]">
              <Clock className="size-3" />
              {formatTime(elapsed)}
            </span>
          )}
          {pending === 'starting' && !isRunning && (
            <span className="flex items-center gap-1 text-xs text-[var(--muted-foreground)]">
              <Loader2 className="size-3 animate-spin" />
              Provisioning...
            </span>
          )}
        </>
      ) : (
        <Button
          variant="secondary"
          size={buttonSize}
          onClick={handleStart}
          disabled={!wsConnected || status === 'DONE' || isBusy}
        >
          {isPair ? <Users className="size-3" /> : <Play className="size-3" />}
          {isPair ? 'Pair' : 'Start'}
        </Button>
      )}
    </div>
  );
}
