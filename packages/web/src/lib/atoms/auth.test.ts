import { describe, it, expect, vi, beforeEach } from 'vitest';
import { createStore } from 'jotai';
import {
  isAuthenticatedAtom,
  isAuthLoadingAtom,
  hydrateAuthAtom,
  logoutAtom,
} from '@/lib/atoms/auth';

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    configureBundledWeb: vi.fn(),
    getHealth: vi.fn(),
    setBaseUrl: vi.fn(),
    setToken: vi.fn(),
  },
}));

vi.mock('@/lib/api/websocket', () => ({
  kaganWs: {
    configure: vi.fn(),
    connect: vi.fn(),
    disconnect: vi.fn(),
  },
}));

describe('auth atoms', () => {
  let store: ReturnType<typeof createStore>;

  beforeEach(() => {
    store = createStore();
    vi.restoreAllMocks();
  });

  it('hydrateAuth sets bundled mode when /health responds ok', async () => {
    const { apiClient } = await import('@/lib/api/client');
    vi.mocked(apiClient.getHealth).mockResolvedValue({ status: 'ok', version: 'test' });
    await store.set(hydrateAuthAtom);
    expect(store.get(isAuthenticatedAtom)).toBe(true);
    expect(store.get(isAuthLoadingAtom)).toBe(false);
  });

  it('hydrateAuth sets unauthenticated state when /health fails', async () => {
    const { apiClient } = await import('@/lib/api/client');
    vi.mocked(apiClient.getHealth).mockRejectedValue(new Error('fail'));
    await store.set(hydrateAuthAtom);
    expect(store.get(isAuthenticatedAtom)).toBe(false);
    expect(store.get(isAuthLoadingAtom)).toBe(false);
  });

  it('logout clears authenticated state', () => {
    store.set(isAuthenticatedAtom, true);
    store.set(logoutAtom);
    expect(store.get(isAuthenticatedAtom)).toBe(false);
    expect(store.get(isAuthLoadingAtom)).toBe(false);
  });
});
