/**
 * useSessionList — polls /api/v1/sessions every 5 s and exposes a sorted
 * session list plus refresh control.
 *
 * Sessions are sorted by `updated_at` descending (most-recent first).
 */

import { useState, useEffect, useCallback } from 'react';
import { apiClient } from '@/lib/api/client';
import type { SessionItemResponse } from '@kagan/shared-api-client';

export interface UseSessionListResult {
  sessions: SessionItemResponse[];
  loading: boolean;
  error: string | null;
  refresh: () => Promise<void>;
}

const POLL_INTERVAL_MS = 5000;

export function useSessionList(): UseSessionListResult {
  const [sessions, setSessions] = useState<SessionItemResponse[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refresh = useCallback(async () => {
    try {
      setLoading(true);
      const response = await apiClient.getSessions();
      const sorted = [...response.sessions].sort(
        (a, b) => b.updated_at.localeCompare(a.updated_at),
      );
      setSessions(sorted);
      setError(null);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to fetch sessions');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    refresh();
    const interval = setInterval(refresh, POLL_INTERVAL_MS);
    return () => clearInterval(interval);
  }, [refresh]);

  return { sessions, loading, error, refresh };
}
