import { atom } from 'jotai';

type ThemeMode = 'system' | 'dark' | 'light';
type ResolvedTheme = 'dark' | 'light';

const MODE_KEY = 'kagan_theme_mode';

export const themeModeAtom = atom<ThemeMode>('system');
export const systemPrefersDarkAtom = atom(true);

export const resolvedThemeAtom = atom<ResolvedTheme>((get) => {
  const mode = get(themeModeAtom);
  if (mode === 'system') {
    return get(systemPrefersDarkAtom) ? 'dark' : 'light';
  }
  return mode;
});

export const setThemeModeAtom = atom(null, (_get, set, mode: ThemeMode) => {
  set(themeModeAtom, mode);
  if (typeof localStorage !== 'undefined') {
    localStorage.setItem(MODE_KEY, mode);
  }
});

export const initThemeAtom = atom(null, (_get, set) => {
  if (typeof localStorage !== 'undefined') {
    const saved = localStorage.getItem(MODE_KEY);
    if (saved === 'system' || saved === 'dark' || saved === 'light') {
      set(themeModeAtom, saved);
    }
  }
  if (typeof window !== 'undefined') {
    const mq = window.matchMedia('(prefers-color-scheme: dark)');
    set(systemPrefersDarkAtom, mq.matches);
    // Listener lives for app lifetime — no cleanup needed
    mq.addEventListener('change', (e) => {
      set(systemPrefersDarkAtom, e.matches);
    });
  }
});
