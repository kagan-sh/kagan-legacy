/**
 * useSessionActions — stop / close actions with capability checks.
 *
 * Each action guards against sessions that do not advertise the matching
 * capability (can_stop / can_close). Attempting to act on an ineligible
 * session is a silent no-op.
 */

import { useState, useCallback } from 'react';
import { apiClient } from '@/lib/api/client';
import type { SessionItemResponse } from '@kagan/shared-api-client';

export interface UseSessionActionsResult {
  /** True while a stop request is in flight. */
  isStopping: boolean;
  /** True while a close request is in flight. */
  isClosing: boolean;
  /** Whether the given session can be stopped. */
  canStop: (session: SessionItemResponse) => boolean;
  /** Whether the given session can be closed. */
  canClose: (session: SessionItemResponse) => boolean;
  /** Request the server stop this session (no-op if !can_stop). */
  stop: (session: SessionItemResponse) => Promise<void>;
  /** Request the server close this session (no-op if !can_close). */
  close: (session: SessionItemResponse) => Promise<void>;
}

export function useSessionActions(): UseSessionActionsResult {
  const [isStopping, setIsStopping] = useState(false);
  const [isClosing, setIsClosing] = useState(false);

  const canStop = useCallback(
    (session: SessionItemResponse) => session.capabilities.can_stop,
    [],
  );

  const canClose = useCallback(
    (session: SessionItemResponse) => session.capabilities.can_close,
    [],
  );

  const stop = useCallback(async (session: SessionItemResponse) => {
    if (!session.capabilities.can_stop) return;
    setIsStopping(true);
    try {
      await apiClient.stopSession(session.id);
    } finally {
      setIsStopping(false);
    }
  }, []);

  const close = useCallback(async (session: SessionItemResponse) => {
    if (!session.capabilities.can_close) return;
    setIsClosing(true);
    try {
      await apiClient.closeSession(session.id);
    } finally {
      setIsClosing(false);
    }
  }, []);

  return {
    isStopping,
    isClosing,
    canStop,
    canClose,
    stop,
    close,
  };
}
