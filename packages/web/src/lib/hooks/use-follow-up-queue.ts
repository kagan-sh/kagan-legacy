import { useState, useEffect, useCallback } from 'react';
import { toast } from 'sonner';
import { kaganWs, type WsInboundMessage } from '@/lib/api/websocket';
import type { UserFollowUp } from '@/components/session/event-stream';
import type { QueuedPrompt } from '@/components/session/follow-up-queue';

let _nextQueueId = 0;
function nextQueueId(): string {
  return `fq-${++_nextQueueId}`;
}

export interface UseFollowUpQueueResult {
  sentFollowUps: UserFollowUp[];
  queue: QueuedPrompt[];
  sendingFollowUp: boolean;
  queuePrompt: (text: string, attachments?: { name: string; type: string }[]) => void;
  removePrompt: (id: string) => void;
  editPrompt: (id: string, text: string) => void;
  interruptAndSend: (id: string) => void;
}

/**
 * Independent state machine for the follow-up prompt queue.
 * Manages queue/remove/edit/send and listens to WS ack/error.
 */
export function useFollowUpQueue(taskId: string | undefined): UseFollowUpQueueResult {
  const [sentFollowUps, setSentFollowUps] = useState<UserFollowUp[]>([]);
  const [queue, setQueue] = useState<QueuedPrompt[]>([]);
  const [sendingFollowUp, setSendingFollowUp] = useState(false);

  // Follow-up ack/error
  useEffect(() => {
    if (!taskId) return;
    const cleanups = [
      kaganWs.on('TASK_FOLLOW_UP_ACK', (data: WsInboundMessage) => {
        if (data.task_id === taskId) setSendingFollowUp(false);
      }),
      kaganWs.on('TASK_FOLLOW_UP_ERROR', (data: WsInboundMessage) => {
        if (data.task_id === taskId) {
          setSendingFollowUp(false);
          toast.error(typeof data.error === 'string' ? data.error : 'Follow-up failed');
        }
      }),
    ];
    return () => cleanups.forEach((fn) => fn());
  }, [taskId]);

  const queuePrompt = useCallback((text: string, attachments?: { name: string; type: string }[]) => {
    const displayText = attachments?.length
      ? `${text} [Attachments: ${attachments.map((a) => a.name).join(', ')}]`
      : text;
    setQueue((prev) => [...prev, { id: nextQueueId(), text: displayText }]);
  }, []);

  const removePrompt = useCallback((id: string) => {
    setQueue((prev) => prev.filter((p) => p.id !== id));
  }, []);

  const editPrompt = useCallback((id: string, text: string) => {
    setQueue((prev) => prev.map((p) => (p.id === id ? { ...p, text } : p)));
  }, []);

  const interruptAndSend = useCallback(
    (id: string) => {
      if (!taskId) return;
      const prompt = queue.find((p) => p.id === id);
      if (!prompt) return;
      setQueue((prev) => prev.filter((p) => p.id !== id));
      setSentFollowUps((prev) => [...prev, { text: prompt.text, timestamp: new Date().toISOString() }]);
      setSendingFollowUp(true);
      kaganWs.sendTaskFollowUp(taskId, prompt.text);
    },
    [taskId, queue],
  );

  return {
    sentFollowUps,
    queue,
    sendingFollowUp,
    queuePrompt,
    removePrompt,
    editPrompt,
    interruptAndSend,
  };
}
