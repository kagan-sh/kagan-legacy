const RELOAD_GUARD_KEY = 'kagan:vite-preload-recovery';
const RELOAD_GUARD_WINDOW_MS = 10_000;

type VitePreloadErrorEvent = Event & {
  payload?: unknown;
};

type PreloadRecoveryTarget = Pick<Window, 'addEventListener' | 'sessionStorage' | 'location'>;

export function installVitePreloadRecovery(target: PreloadRecoveryTarget = window): void {
  target.addEventListener('vite:preloadError', (event: Event) => {
    const preloadEvent = event as VitePreloadErrorEvent;
    preloadEvent.preventDefault();

    const lastReloadAtRaw = target.sessionStorage.getItem(RELOAD_GUARD_KEY);
    const lastReloadAt = lastReloadAtRaw === null ? null : Number(lastReloadAtRaw);
    const now = Date.now();

    if (
      lastReloadAt !== null &&
      Number.isFinite(lastReloadAt) &&
      now - lastReloadAt < RELOAD_GUARD_WINDOW_MS
    ) {
      return;
    }

    target.sessionStorage.setItem(RELOAD_GUARD_KEY, String(now));
    target.location.reload();
  });
}
