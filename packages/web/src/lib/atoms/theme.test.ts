import { describe, it, expect, beforeEach } from 'vitest';
import { createStore } from 'jotai';
import {
  themeModeAtom,
  systemPrefersDarkAtom,
  resolvedThemeAtom,
} from '@/lib/atoms/theme';

describe('theme atoms', () => {
  let store: ReturnType<typeof createStore>;

  beforeEach(() => {
    store = createStore();
  });

  it('resolves system to dark when system prefers dark', () => {
    store.set(themeModeAtom, 'system');
    store.set(systemPrefersDarkAtom, true);
    expect(store.get(resolvedThemeAtom)).toBe('dark');
  });

  it('resolves system to light when system prefers light', () => {
    store.set(themeModeAtom, 'system');
    store.set(systemPrefersDarkAtom, false);
    expect(store.get(resolvedThemeAtom)).toBe('light');
  });

  it('respects explicit dark mode', () => {
    store.set(themeModeAtom, 'dark');
    store.set(systemPrefersDarkAtom, false);
    expect(store.get(resolvedThemeAtom)).toBe('dark');
  });

  it('respects explicit light mode', () => {
    store.set(themeModeAtom, 'light');
    store.set(systemPrefersDarkAtom, true);
    expect(store.get(resolvedThemeAtom)).toBe('light');
  });
});
