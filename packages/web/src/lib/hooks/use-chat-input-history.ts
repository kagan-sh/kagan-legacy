import { useRef, useEffect, useCallback } from 'react';
import { ChatHistory, HistoryCursor } from '@/lib/chat-history';

export function useChatInputHistory(projectId?: string, persistHistory?: boolean) {
  const historyRef = useRef<ChatHistory | null>(null);
  const cursorRef = useRef<HistoryCursor>(new HistoryCursor());

  useEffect(() => {
    const pid = projectId ?? '__default__';
    const persist = (persistHistory ?? true) && pid !== '__default__';
    historyRef.current = new ChatHistory(pid, persist);
    cursorRef.current.reset();
  }, [projectId, persistHistory]);

  const getEntries = useCallback(() => {
    return historyRef.current?.getEntries() ?? [];
  }, []);

  const push = useCallback((text: string) => {
    historyRef.current?.push(text);
  }, []);

  const navigateUp = useCallback((currentText: string) => {
    const entries = getEntries();
    return cursorRef.current.up(currentText, entries);
  }, [getEntries]);

  const navigateDown = useCallback(() => {
    const entries = getEntries();
    return cursorRef.current.down(entries);
  }, [getEntries]);

  const reset = useCallback(() => {
    cursorRef.current.reset();
  }, []);

  return { push, navigateUp, navigateDown, reset, getEntries };
}
