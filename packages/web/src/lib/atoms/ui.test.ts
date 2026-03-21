import { describe, it, expect, beforeEach } from 'vitest';
import { createStore } from 'jotai';
import {
  rightRailModeAtom,
  rightRailTaskIdAtom,
  commandPaletteOpenAtom,
} from '@/lib/atoms/ui';

describe('ui atoms', () => {
  let store: ReturnType<typeof createStore>;

  beforeEach(() => {
    store = createStore();
  });

  describe('rightRailModeAtom', () => {
    it('defaults to none', () => {
      expect(store.get(rightRailModeAtom)).toBe('none');
    });

    it('transitions to right-docked chat', () => {
      store.set(rightRailModeAtom, 'chat-right');
      expect(store.get(rightRailModeAtom)).toBe('chat-right');
    });

    it('supports all chat layouts', () => {
      store.set(rightRailModeAtom, 'chat-bottom');
      expect(store.get(rightRailModeAtom)).toBe('chat-bottom');

      store.set(rightRailModeAtom, 'chat-fullscreen');
      expect(store.get(rightRailModeAtom)).toBe('chat-fullscreen');
    });

    it('transitions back to none', () => {
      store.set(rightRailModeAtom, 'chat-right');
      store.set(rightRailModeAtom, 'none');
      expect(store.get(rightRailModeAtom)).toBe('none');
    });
  });

  describe('rightRailTaskIdAtom', () => {
    it('defaults to null', () => {
      expect(store.get(rightRailTaskIdAtom)).toBeNull();
    });

    it('sets task id', () => {
      store.set(rightRailTaskIdAtom, 'task-123');
      expect(store.get(rightRailTaskIdAtom)).toBe('task-123');
    });

    it('clears task id', () => {
      store.set(rightRailTaskIdAtom, 'task-123');
      store.set(rightRailTaskIdAtom, null);
      expect(store.get(rightRailTaskIdAtom)).toBeNull();
    });
  });

  describe('commandPaletteOpenAtom', () => {
    it('defaults to false', () => {
      expect(store.get(commandPaletteOpenAtom)).toBe(false);
    });

    it('opens Quick Actions', () => {
      store.set(commandPaletteOpenAtom, true);
      expect(store.get(commandPaletteOpenAtom)).toBe(true);
    });

    it('closes Quick Actions', () => {
      store.set(commandPaletteOpenAtom, true);
      store.set(commandPaletteOpenAtom, false);
      expect(store.get(commandPaletteOpenAtom)).toBe(false);
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
