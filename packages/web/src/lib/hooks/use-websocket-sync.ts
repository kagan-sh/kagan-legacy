import { useEffect } from 'react';
import { useAtomValue, useSetAtom } from 'jotai';
import { kaganWs } from '@/lib/api/websocket';
import { wsConnectedAtom, reconnectAttemptsAtom } from '@/lib/atoms/connection';
import { tasksAtom, fetchTasksAtom, projectSwitchVersionAtom } from '@/lib/atoms/board';
import { isAnyDialogOpenAtom } from '@/lib/atoms/ui';
import { apiClient } from '@/lib/api/client';
import type { WsInboundMessage } from '@/lib/api/websocket';
import type { WireTask } from '@/lib/api/types';

export function useWebSocketSync() {
  const setWsConnected = useSetAtom(wsConnectedAtom);
  const setReconnectAttempts = useSetAtom(reconnectAttemptsAtom);
  const setTasks = useSetAtom(tasksAtom);
  const fetchTasks = useSetAtom(fetchTasksAtom);
  const projectVersion = useAtomValue(projectSwitchVersionAtom);
  const wsConnected = useAtomValue(wsConnectedAtom);
  const isAnyDialogOpen = useAtomValue(isAnyDialogOpenAtom);

  useEffect(() => {
    const cleanups = [
      kaganWs.on('connected', () => {
        setWsConnected(true);
        setReconnectAttempts(0);
        kaganWs.subscribeToBoardUpdates();
      }),
      kaganWs.on('disconnected', () => {
        setWsConnected(false);
        setReconnectAttempts((prev) => prev + 1);
      }),
      kaganWs.on('BOARD_SYNC', (data: WsInboundMessage) => {
        if (Array.isArray(data.tasks)) {
          setTasks(data.tasks as WireTask[]);
        }
      }),
      kaganWs.on('TASK_UPDATED', async (data: WsInboundMessage) => {
        if (data.task_id) {
          try {
            const task = await apiClient.getTask(data.task_id);
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
      }),
    ];

    // Connect if configured
    if (!kaganWs.isConnected()) {
      kaganWs.connect();
    } else {
      kaganWs.subscribeToBoardUpdates();
    }

    return () => {
      cleanups.forEach((fn) => fn());
    };
  }, [setWsConnected, setReconnectAttempts, setTasks, fetchTasks]);

  // Adaptive polling fallback when WebSocket is disconnected
  useEffect(() => {
    if (wsConnected || isAnyDialogOpen) return;
    const interval = setInterval(() => fetchTasks(), 10_000);
    return () => clearInterval(interval);
  }, [wsConnected, isAnyDialogOpen, fetchTasks]);

  // Re-subscribe to board updates when the active project changes
  useEffect(() => {
    if (projectVersion > 0 && kaganWs.isConnected()) {
      kaganWs.subscribeToBoardUpdates();
    }
  }, [projectVersion]);
}
