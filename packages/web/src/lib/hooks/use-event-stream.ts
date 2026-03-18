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
import { apiClient } from '@/lib/api/client';
import { streamSSE } from '@/lib/api/sse';
import {
  sseConnectedAtom,
  reconnectAttemptsAtom,
} from '@/lib/atoms/connection';
import {
  tasksAtom,
  fetchTasksAtom,
  projectSwitchVersionAtom,
} from '@/lib/atoms/board';
import { isAnyDialogOpenAtom } from '@/lib/atoms/ui';
import type { WireEvent } from '@/lib/api/types';

interface SSEMessage {
  type: string;
  task_id?: string;
  event?: WireEvent;
}

export function useEventStream() {
  const setSseConnected = useSetAtom(sseConnectedAtom);
  const setReconnectAttempts = useSetAtom(reconnectAttemptsAtom);
  const setTasks = useSetAtom(tasksAtom);
  const fetchTasks = useSetAtom(fetchTasksAtom);
  const projectVersion = useAtomValue(projectSwitchVersionAtom);
  const sseConnected = useAtomValue(sseConnectedAtom);
  const isAnyDialogOpen = useAtomValue(isAnyDialogOpenAtom);

  // Ref to track abort controller for cleanup
  const abortRef = useRef<AbortController | null>(null);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    let attempts = 0;

    const connect = () => {
      // Clean up previous
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;

      (async () => {
        let streamEstablished = false;
        try {
          setSseConnected(true);
          setReconnectAttempts(0);

          // Initial board fetch on connect
          fetchTasks();

          for await (const msg of streamSSE<SSEMessage>('/api/events/stream', {
            signal: controller.signal,
          })) {
            // Reset backoff once stream delivers its first message
            if (!streamEstablished) {
              streamEstablished = true;
              attempts = 0;
            }
            if (msg.type === 'TASK_UPDATED') {
              if (msg.task_id) {
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
            attempts += 1;
            setReconnectAttempts(attempts);
            // Exponential backoff: 1s, 2s, 4s, ... max 30s
            const delay = Math.min(1000 * 2 ** attempts, 30_000);
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
  }, [setSseConnected, setReconnectAttempts, setTasks, fetchTasks]);

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

  // Recover from browser tab backgrounding
  useEffect(() => {
    const onVisible = () => {
      if (document.visibilityState !== 'visible') return;
      fetchTasks();
      // If disconnected, force reconnect
      if (!abortRef.current || abortRef.current.signal.aborted) {
        // The reconnect timer will handle it
      }
    };
    document.addEventListener('visibilitychange', onVisible);
    return () => document.removeEventListener('visibilitychange', onVisible);
  }, [fetchTasks]);
}
