import { describe, it, expect } from 'vitest';
import { createStore } from 'jotai';
import { isStreamingAtom } from '@/lib/atoms/chat';

describe('isStreamingAtom', () => {
  it('defaults to false', () => {
    const store = createStore();
    expect(store.get(isStreamingAtom)).toBe(false);
  });

  it('can be set to true', () => {
    const store = createStore();
    store.set(isStreamingAtom, true);
    expect(store.get(isStreamingAtom)).toBe(true);
  });

  it('can be reset to false', () => {
    const store = createStore();
    store.set(isStreamingAtom, true);
    store.set(isStreamingAtom, false);
    expect(store.get(isStreamingAtom)).toBe(false);
  });
});
