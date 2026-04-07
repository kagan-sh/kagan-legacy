import { describe, it, expect, beforeEach } from 'vitest';
import { createStore } from 'jotai';
import {
  rightRailModeAtom,
  rightRailTaskIdAtom,
} from '@/lib/atoms/ui';

describe('ui atoms', () => {
  let store: ReturnType<typeof createStore>;

  beforeEach(() => {
    store = createStore();
  });

  describe('rightRailModeAtom', () => {
    it('supports all chat layouts', () => {
      store.set(rightRailModeAtom, 'chat-right');
      expect(store.get(rightRailModeAtom)).toBe('chat-right');

      store.set(rightRailModeAtom, 'chat-bottom');
      expect(store.get(rightRailModeAtom)).toBe('chat-bottom');

      store.set(rightRailModeAtom, 'chat-fullscreen');
      expect(store.get(rightRailModeAtom)).toBe('chat-fullscreen');
    });
  });

  describe('right-rail state transitions', () => {
    it('opens chat with task id', () => {
      store.set(rightRailModeAtom, 'chat-right');
      store.set(rightRailTaskIdAtom, 'task-123');

      expect(store.get(rightRailModeAtom)).toBe('chat-right');
      expect(store.get(rightRailTaskIdAtom)).toBe('task-123');
    });

    it('closes panel and clears ids', () => {
      store.set(rightRailModeAtom, 'chat-bottom');
      store.set(rightRailTaskIdAtom, 'task-123');

      store.set(rightRailModeAtom, 'none');
      store.set(rightRailTaskIdAtom, null);

      expect(store.get(rightRailModeAtom)).toBe('none');
      expect(store.get(rightRailTaskIdAtom)).toBeNull();
    });
  });
});
