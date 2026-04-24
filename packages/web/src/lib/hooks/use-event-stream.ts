/**
 * SSE-based event stream hook — replaces WebSocket sync.
 *
 * Connects to GET /api/events/stream via SSE and dispatches
 * TASK_UPDATED / SESSION_EVENT to jotai atoms. Auto-reconnects
 * with exponential backoff. Falls back to HTTP polling when the
 * tab is backgrounded.
 */

import { useEffect, useRef } from 'react';
import { useAtomValue, useSetAtom } from 'jotai';
import { useLocation } from 'react-router';
import { apiClient } from '@/lib/api/client';
import { streamSSE } from '@/lib/api/sse';
import { sseConnectedAtom } from '@/lib/atoms/connection';
import {
  tasksAtom,
  fetchTasksAtom,
  projectSwitchVersionAtom,
} from '@/lib/atoms/board';
import { presenceAtom } from '@/lib/atoms/presence';
import { isAnyDialogOpenAtom } from '@/lib/atoms/ui';
import type { WireEvent, WireTask } from '@/lib/api/types';

interface SSEMessage {
  type: string;
  task_id?: string;
  task?: WireTask;
  event?: WireEvent;
}

export function useEventStream() {
  const location = useLocation();
  const setSseConnected = useSetAtom(sseConnectedAtom);
  const setTasks = useSetAtom(tasksAtom);
  const setPresence = useSetAtom(presenceAtom);
  const fetchTasks = useSetAtom(fetchTasksAtom);
  const projectVersion = useAtomValue(projectSwitchVersionAtom);
  const sseConnected = useAtomValue(sseConnectedAtom);
  const isAnyDialogOpen = useAtomValue(isAnyDialogOpenAtom);

  // Ref to track abort controller for cleanup
  const abortRef = useRef<AbortController | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const presenceClientIdRef = useRef<string | null>(null);

  if (!presenceClientIdRef.current) {
    try {
      const key = 'kagan.web.presence.client_id';
      const existing = window.sessionStorage.getItem(key);
      if (existing) {
        presenceClientIdRef.current = existing;
      } else {
        const next = window.crypto?.randomUUID?.() ?? `web-${Date.now().toString(36)}`;
        window.sessionStorage.setItem(key, next);
        presenceClientIdRef.current = next;
      }
    } catch {
      presenceClientIdRef.current = `web-${Date.now().toString(36)}`;
    }
  }

  const currentTaskId = /^\/task\/([^/?]+)/.exec(location.pathname)?.[1] ?? null;

  useEffect(() => {
    const connect = () => {
      // Clean up previous
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      (async () => {
        let streamEstablished = false;
        try {
          setSseConnected(true);

          // Initial board fetch on connect
          fetchTasks();
          apiClient.getPresence().then(setPresence).catch(() => {});

          const query = new URLSearchParams({
            client_type: 'web',
            client_id: presenceClientIdRef.current ?? 'web',
          });

          for await (const msg of streamSSE<SSEMessage>(`/api/events/stream?${query.toString()}`, {
            signal: controller.signal,
          })) {
            // Reset backoff once stream delivers its first message
            if (!streamEstablished) {
              streamEstablished = true;
              reconnectAttemptsRef.current = 0;
            }
            if (msg.type === 'TASK_UPDATED') {
              if (msg.task) {
                const task = msg.task;
                setTasks((prev) => {
                  const index = prev.findIndex((t) => t.id === task.id);
                  if (index >= 0) {
                    const next = [...prev];
                    next[index] = task;
                    return next;
                  }
                  return [...prev, task];
                });
              } else if (msg.task_id) {
                try {
                  const task = await apiClient.getTask(msg.task_id);
                  setTasks((prev) => {
                    const index = prev.findIndex((t) => t.id === task.id);
                    if (index >= 0) {
                      const next = [...prev];
                      next[index] = task;
                      return next;
                    }
                    return [...prev, task];
                  });
                } catch {
                  fetchTasks();
                }
              } else {
                fetchTasks();
              }
            }
            // SESSION_EVENT is dispatched to subscribers via a custom event
            if (msg.type === 'SESSION_EVENT' && msg.event) {
              window.dispatchEvent(
                new CustomEvent('kagan:session-event', {
                  detail: { task_id: msg.task_id, event: msg.event },
                }),
              );
              // Keep board card timestamps fresh during active sessions
              const eventTs = msg.event.created_at;
              const eventTaskId = msg.task_id;
              if (eventTaskId && eventTs) {
                setTasks((prev) => {
                  const idx = prev.findIndex((t) => t.id === eventTaskId);
                  if (idx < 0) return prev;
                  const existing = prev[idx]!;
                  if (existing.last_event_at && existing.last_event_at >= eventTs) return prev;
                  const next = [...prev];
                  next[idx] = { ...existing, last_event_at: eventTs };
                  return next;
                });
              }
            }
          }
        } catch (err) {
          if (controller.signal.aborted) return;
          console.warn('[SSE] Stream disconnected:', err);
        } finally {
          if (!controller.signal.aborted) {
            setSseConnected(false);
            reconnectAttemptsRef.current += 1;
            // Exponential backoff: 1s, 2s, 4s, ... max 30s
            const delay = Math.min(1000 * 2 ** reconnectAttemptsRef.current, 30_000);
            reconnectTimerRef.current = setTimeout(connect, delay);
          }
        }
      })();
    };

    connect();

    return () => {
      abortRef.current?.abort();
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
    };
  }, [setSseConnected, setTasks, setPresence, fetchTasks, projectVersion]);

  // Adaptive polling fallback when SSE is disconnected
  useEffect(() => {
    if (sseConnected || isAnyDialogOpen) return;
    const interval = setInterval(() => {
      if (document.visibilityState === 'visible') fetchTasks();
    }, 10_000);
    return () => clearInterval(interval);
  }, [sseConnected, isAnyDialogOpen, fetchTasks]);

  // Re-fetch board when active project changes
  useEffect(() => {
    if (projectVersion > 0) {
      fetchTasks();
    }
  }, [projectVersion, fetchTasks]);

  useEffect(() => {
    const clientId = presenceClientIdRef.current;
    if (!clientId) return;

    let cancelled = false;
    const syncPresence = async () => {
      try {
        await apiClient.sendPresenceHeartbeat({
          client_id: clientId,
          client_type: 'web',
          active_task_id: currentTaskId,
        });
        const presence = await apiClient.getPresence();
        if (!cancelled) {
          setPresence(presence);
        }
      } catch {
        if (!cancelled && !sseConnected) {
          setPresence([]);
        }
      }
    };

    void syncPresence();
    const interval = window.setInterval(() => {
      if (document.visibilityState === 'visible') {
        void syncPresence();
      }
    }, 25_000);

    return () => {
      cancelled = true;
      window.clearInterval(interval);
    };
  }, [currentTaskId, sseConnected, setPresence]);

  // Recover from browser tab backgrounding — only fetch if SSE is disconnected
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState !== 'visible') return;
      if (!abortRef.current || abortRef.current.signal.aborted) {
        fetchTasks();
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [fetchTasks]);
}
