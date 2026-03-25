const DIFF_VIEW_MODE_KEY = 'kagan_diff_view_mode';
const WEB_ONBOARDING_TUTORIAL_SEEN_KEY = 'kagan_web_onboarding_tutorial_seen_v1';

export type DiffViewModePreference = 'split' | 'unified';

type StorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

function getStorage(): StorageLike | null {
  if (typeof globalThis === 'undefined') {
    return null;
  }

  const storage = globalThis.localStorage;
  if (
    storage == null ||
    typeof storage.getItem !== 'function' ||
    typeof storage.setItem !== 'function' ||
    typeof storage.removeItem !== 'function'
  ) {
    return null;
  }

  return storage;
}

export function saveDiffViewMode(mode: DiffViewModePreference): void {
  const storage = getStorage();
  if (storage === null) return;
  storage.setItem(DIFF_VIEW_MODE_KEY, mode);
}

export function loadDiffViewMode(): DiffViewModePreference | null {
  const storage = getStorage();
  if (storage === null) return null;
  const saved = storage.getItem(DIFF_VIEW_MODE_KEY);
  if (saved === 'split' || saved === 'unified') {
    return saved;
  }
  return null;
}

export function saveWebOnboardingTutorialSeen(value: boolean): void {
  const storage = getStorage();
  if (storage === null) return;
  if (value) {
    storage.setItem(WEB_ONBOARDING_TUTORIAL_SEEN_KEY, '1');
    return;
  }
  storage.removeItem(WEB_ONBOARDING_TUTORIAL_SEEN_KEY);
}

export function loadWebOnboardingTutorialSeen(): boolean {
  const storage = getStorage();
  if (storage === null) return false;
  return storage.getItem(WEB_ONBOARDING_TUTORIAL_SEEN_KEY) === '1';
}

