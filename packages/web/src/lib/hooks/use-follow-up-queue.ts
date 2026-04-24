import { useState, useCallback } from 'react';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api/client';
import type { UserFollowUp } from '@/components/session/event-stream';
import type { QueuedPrompt } from '@/components/session/follow-up-queue';

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
 * Manages queue/remove/edit/send via REST POST /api/tasks/:id/follow-up.
 */
export function useFollowUpQueue(taskId: string | undefined): UseFollowUpQueueResult {
  const [sentFollowUps, setSentFollowUps] = useState<UserFollowUp[]>([]);
  const [queue, setQueue] = useState<QueuedPrompt[]>([]);
  const [sendingFollowUp, setSendingFollowUp] = useState(false);

  const queuePrompt = useCallback((text: string, attachments?: { name: string; type: string }[]) => {
    const displayText = attachments?.length
      ? `${text} [Attachments: ${attachments.map((a) => a.name).join(', ')}]`
      : text;
    setQueue((prev) => [...prev, { id: crypto.randomUUID(), text: displayText }]);
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

      apiClient.sendTaskFollowUp(taskId, prompt.text)
        .then(() => setSendingFollowUp(false))
        .catch((err) => {
          setSendingFollowUp(false);
          toast.error(err instanceof Error ? err.message : 'Follow-up failed');
        });
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
