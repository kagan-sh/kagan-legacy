import { describe, it, expect, beforeEach } from 'vitest';
import { createStore } from 'jotai';
import {
  selectedSessionAtom,
  sessionOverlayOpenAtom,
  sessionOverlayLayoutAtom,
} from '@/lib/atoms/ui';

describe('ui atoms', () => {
  let store: ReturnType<typeof createStore>;

  beforeEach(() => {
    store = createStore();
  });

  describe('session overlay atoms', () => {
    it('stores and retrieves selected session', () => {
      const session = {
        id: 'sess-1',
        type: 'chat',
        role: null,
        status: 'active',
        title: 'Test Session',
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

      store.set(selectedSessionAtom, session);
      expect(store.get(selectedSessionAtom)).toEqual(session);
    });

    it('toggles overlay open state', () => {
      expect(store.get(sessionOverlayOpenAtom)).toBe(false);
      store.set(sessionOverlayOpenAtom, true);
      expect(store.get(sessionOverlayOpenAtom)).toBe(true);
    });

    it('defaults layout to docked', () => {
      expect(store.get(sessionOverlayLayoutAtom)).toBe('docked');
    });

    it('can switch layout to fullscreen', () => {
      store.set(sessionOverlayLayoutAtom, 'fullscreen');
      expect(store.get(sessionOverlayLayoutAtom)).toBe('fullscreen');
    });

  });
});
