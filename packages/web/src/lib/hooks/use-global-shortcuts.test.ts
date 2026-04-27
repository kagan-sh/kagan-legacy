import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { createStore, Provider } from 'jotai';
import { fireEvent, render } from '@testing-library/react';
import { createElement, type ReactNode } from 'react';
import { commandPaletteOpenAtom } from '@/lib/atoms/ui';
import { useGlobalShortcuts } from '@/lib/hooks/use-global-shortcuts';

function Harness() {
  useGlobalShortcuts();
  return null;
}

function renderHarness(store: ReturnType<typeof createStore>) {
  function Wrapper({ children }: { children: ReactNode }) {
    return createElement(Provider, { store }, children);
  }
  return render(createElement(Harness), { wrapper: Wrapper });
}

describe('useGlobalShortcuts', () => {
  let store: ReturnType<typeof createStore>;

  beforeEach(() => {
    store = createStore();
  });

  afterEach(() => {
    // Let React Testing Library's afterEach handle unmount cleanup.
  });

  it('opens the palette on Cmd+K', () => {
    renderHarness(store);
    expect(store.get(commandPaletteOpenAtom)).toBe(false);

    fireEvent.keyDown(document, { key: 'k', metaKey: true });
    expect(store.get(commandPaletteOpenAtom)).toBe(true);
  });

  it('opens the palette on Ctrl+K', () => {
    renderHarness(store);

    fireEvent.keyDown(document, { key: 'k', ctrlKey: true });
    expect(store.get(commandPaletteOpenAtom)).toBe(true);
  });

  it('toggles closed when already open', () => {
    store.set(commandPaletteOpenAtom, true);
    renderHarness(store);

    fireEvent.keyDown(document, { key: 'k', metaKey: true });
    expect(store.get(commandPaletteOpenAtom)).toBe(false);
  });

  it('ignores plain k with no modifier', () => {
    renderHarness(store);

    fireEvent.keyDown(document, { key: 'k' });
    expect(store.get(commandPaletteOpenAtom)).toBe(false);
  });

  it('ignores Cmd+Shift+K (reserved for the session switcher)', () => {
    renderHarness(store);

    fireEvent.keyDown(document, { key: 'k', metaKey: true, shiftKey: true });
    expect(store.get(commandPaletteOpenAtom)).toBe(false);
  });

  it('ignores Cmd+Alt+K', () => {
    renderHarness(store);

    fireEvent.keyDown(document, { key: 'k', metaKey: true, altKey: true });
    expect(store.get(commandPaletteOpenAtom)).toBe(false);
  });

  it('preventDefaults the keydown so browsers do not steal the shortcut', () => {
    renderHarness(store);

    const event = new KeyboardEvent('keydown', {
      key: 'k',
      metaKey: true,
      bubbles: true,
      cancelable: true,
    });
    document.dispatchEvent(event);
    expect(event.defaultPrevented).toBe(true);
  });

  it('intercepts Cmd+K even when focus is inside an editable target', () => {
    renderHarness(store);

    const input = document.createElement('input');
    document.body.appendChild(input);
    input.focus();

    fireEvent.keyDown(input, { key: 'k', metaKey: true });
    expect(store.get(commandPaletteOpenAtom)).toBe(true);

    document.body.removeChild(input);
  });

  it('cleans up the listener on unmount', () => {
    const { unmount } = renderHarness(store);
    unmount();

    fireEvent.keyDown(document, { key: 'k', metaKey: true });
    expect(store.get(commandPaletteOpenAtom)).toBe(false);
  });

  it('is case-insensitive', () => {
    renderHarness(store);

    fireEvent.keyDown(document, { key: 'K', metaKey: true });
    expect(store.get(commandPaletteOpenAtom)).toBe(true);
  });
});
