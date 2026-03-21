import { describe, expect, it, vi } from 'vitest';
import { installVitePreloadRecovery } from './vite-preload-recovery';

class MockSessionStorage {
  private values = new Map<string, string>();

  getItem(key: string): string | null {
    return this.values.get(key) ?? null;
  }

  setItem(key: string, value: string): void {
    this.values.set(key, value);
  }
}

class MockTarget extends EventTarget {
  sessionStorage = new MockSessionStorage();
  location = { reload: vi.fn() };
}

describe('installVitePreloadRecovery', () => {
  it('reloads once when a Vite preload error occurs', () => {
    const target = new MockTarget();
    vi.spyOn(Date, 'now').mockReturnValue(1_000);

    installVitePreloadRecovery(target as unknown as Window);

    const event = new Event('vite:preloadError', { cancelable: true });
    target.dispatchEvent(event);

    expect(event.defaultPrevented).toBe(true);
    expect(target.location.reload).toHaveBeenCalledTimes(1);

    vi.restoreAllMocks();
  });

  it('does not reload repeatedly inside the guard window', () => {
    const target = new MockTarget();
    installVitePreloadRecovery(target as unknown as Window);

    vi.spyOn(Date, 'now').mockReturnValue(1_000);
    target.dispatchEvent(new Event('vite:preloadError', { cancelable: true }));

    vi.spyOn(Date, 'now').mockReturnValue(5_000);
    target.dispatchEvent(new Event('vite:preloadError', { cancelable: true }));

    expect(target.location.reload).toHaveBeenCalledTimes(1);

    vi.restoreAllMocks();
  });
});
