import { atom } from 'jotai';
import { apiClient } from '@/lib/api/client';

export const isAuthenticatedAtom = atom(false);
export const isAuthLoadingAtom = atom(true);

export const hydrateAuthAtom = atom(null, async (_get, set) => {
  set(isAuthLoadingAtom, true);

  try {
    await apiClient.getHealth();
    apiClient.configureBundledWeb();
    set(isAuthenticatedAtom, true);
    set(isAuthLoadingAtom, false);
    return;
  } catch {}

  set(isAuthenticatedAtom, false);
  set(isAuthLoadingAtom, false);
});

export const retryHealthCheckAtom = atom(null, async (_get, set) => {
  set(isAuthLoadingAtom, true);
  try {
    await apiClient.getHealth();
    apiClient.configureBundledWeb();
    set(isAuthenticatedAtom, true);
    set(isAuthLoadingAtom, false);
    return true;
  } catch {
    // Still not reachable
  }
  set(isAuthLoadingAtom, false);
  return false;
});

export const logoutAtom = atom(null, (_get, set) => {
  set(isAuthenticatedAtom, false);
  set(isAuthLoadingAtom, false);
});
