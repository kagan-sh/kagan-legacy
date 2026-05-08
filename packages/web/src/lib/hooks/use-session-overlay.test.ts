/**
 * Unit tests for useSessionOverlay.
 */

import { describe, expect, it, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { createStore, Provider } from 'jotai';
import { createElement, type ReactNode } from 'react';

import { useSessionOverlay } from '@/lib/hooks/use-session-overlay';
import {
  selectedSessionAtom,
  sessionOverlayLayoutAtom,
} from '@/lib/atoms/ui';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeSession(id: string): NonNullable<ReturnType<typeof useSessionOverlay>['selectedSession']> {
  return {
    id,
    type: 'chat',
    role: null,
    status: 'active',
    title: `Session ${id}`,
    backend: 'claude',
    project_id: null,
    task_id: null,
    session_id: null,
    chat_session_id: null,
    updated_at: '2026-05-08T12:00:00Z',
    capabilities: {
      can_chat: true,
      can_stream: true,
      can_replay: true,
      can_stop: true,
      can_close: true,
      has_kagan_tools: true,
    },
  };
}

function renderWithStore<T>(hook: () => T, store: ReturnType<typeof createStore>) {
  const wrapper = ({ children }: { children: ReactNode }) =>
    createElement(Provider, { store }, children);
  return renderHook(hook, { wrapper });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('useSessionOverlay', () => {
  let store: ReturnType<typeof createStore>;

  beforeEach(() => {
    store = createStore();
  });

  it('defaults to closed with no selected session', () => {
    const { result } = renderWithStore(() => useSessionOverlay(), store);

    expect(result.current.isOpen).toBe(false);
    expect(result.current.selectedSession).toBeNull();
    expect(result.current.layout).toBe('docked');
  });

  it('opens overlay with a session', () => {
    const { result } = renderWithStore(() => useSessionOverlay(), store);
    const session = makeSession('sess-1');

    act(() => {
      result.current.open(session);
    });

    expect(result.current.isOpen).toBe(true);
    expect(result.current.selectedSession?.id).toBe('sess-1');
  });

  it('opens overlay in fullscreen when requested', () => {
    const { result } = renderWithStore(() => useSessionOverlay(), store);
    const session = makeSession('sess-1');

    act(() => {
      result.current.open(session, 'fullscreen');
    });

    expect(result.current.isOpen).toBe(true);
    expect(result.current.layout).toBe('fullscreen');
  });

  it('closes overlay without clearing selection', () => {
    const { result } = renderWithStore(() => useSessionOverlay(), store);
    const session = makeSession('sess-1');

    act(() => {
      result.current.open(session);
    });
    act(() => {
      result.current.close();
    });

    expect(result.current.isOpen).toBe(false);
    expect(result.current.selectedSession?.id).toBe('sess-1');
  });

  it('toggles open state', () => {
    const { result } = renderWithStore(() => useSessionOverlay(), store);
    const session = makeSession('sess-1');

    act(() => {
      result.current.selectSession(session);
    });

    act(() => {
      result.current.toggle();
    });
    expect(result.current.isOpen).toBe(true);

    act(() => {
      result.current.toggle();
    });
    expect(result.current.isOpen).toBe(false);
  });

  it('changes layout via setLayout', () => {
    const { result } = renderWithStore(() => useSessionOverlay(), store);

    act(() => {
      result.current.setLayout('fullscreen');
    });

    expect(store.get(sessionOverlayLayoutAtom)).toBe('fullscreen');
    expect(result.current.layout).toBe('fullscreen');
  });

  it('selectSession updates the selected session atom', () => {
    const { result } = renderWithStore(() => useSessionOverlay(), store);
    const sessionA = makeSession('sess-a');
    const sessionB = makeSession('sess-b');

    act(() => {
      result.current.selectSession(sessionA);
    });
    expect(store.get(selectedSessionAtom)?.id).toBe('sess-a');

    act(() => {
      result.current.selectSession(sessionB);
    });
    expect(store.get(selectedSessionAtom)?.id).toBe('sess-b');

    act(() => {
      result.current.selectSession(null);
    });
    expect(store.get(selectedSessionAtom)).toBeNull();
  });
});
