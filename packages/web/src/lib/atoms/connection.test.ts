import { describe, it, expect } from 'vitest';
import { createStore } from 'jotai';
import { wsConnectedAtom, reconnectAttemptsAtom } from '@/lib/atoms/connection';

describe('connection atoms', () => {
  it('initial state is disconnected', () => {
    const store = createStore();
    expect(store.get(wsConnectedAtom)).toBe(false);
    expect(store.get(reconnectAttemptsAtom)).toBe(0);
  });
});
