import { useSyncExternalStore } from "react";

function subscribe(callback: () => void) {
    document.addEventListener("visibilitychange", callback);
    return () => document.removeEventListener("visibilitychange", callback);
}

function getSnapshot() {
    return document.visibilityState === "visible";
}

function getServerSnapshot() {
    return true;
}

/** Returns `true` when the browser tab is visible, `false` when hidden. */
export function usePageVisible(): boolean {
    return useSyncExternalStore(subscribe, getSnapshot, getServerSnapshot);
}
