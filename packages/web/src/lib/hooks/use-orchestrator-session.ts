import { useCallback } from 'react';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api/client';
import type { WireChatSessionSummary } from '@/lib/api/types';

interface UseOrchestratorSessionOptions {
  onSessionCreated?: (sessionId: string) => void;
  onError?: (error: string) => void;
}

export function useOrchestratorSession(options?: UseOrchestratorSessionOptions) {
  const { onSessionCreated, onError } = options || {};

  const createOrGetSession = useCallback(
    async (sessions: WireChatSessionSummary[]): Promise<string | null> => {
      try {
        const orchestratorSessions = sessions
          .filter((s) =>
            ['orchestrator', 'web'].includes(s.source.toLowerCase()),
          )
          .sort((a, b) => b.updated_at.localeCompare(a.updated_at));

        let sessionId: string;
        if (orchestratorSessions.length > 0) {
          sessionId = orchestratorSessions[0]!.id;
        } else {
          const created = await apiClient.createChatSession({});
          sessionId = created.id;
        }

        onSessionCreated?.(sessionId);
        return sessionId;
      } catch (error) {
        const message =
          error instanceof Error ? error.message : 'Failed to create session';
        onError?.(message);
        toast.error(message);
        return null;
      }
    },
    [onSessionCreated, onError],
  );

  return { createOrGetSession };
}
