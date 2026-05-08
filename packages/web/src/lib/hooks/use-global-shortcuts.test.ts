import { afterEach, beforeEach, describe, expect, it } from 'vitest';
import { createStore, Provider } from 'jotai';
import { fireEvent, render } from '@testing-library/react';
import { createElement, type ReactNode } from 'react';
import { MemoryRouter, useLocation } from 'react-router';
import {
  commandPaletteOpenAtom,
  helpOverlayOpenAtom,
  sessionPickerOpenAtom,
  sessionOverlayOpenAtom,
  sessionOverlayLayoutAtom,
} from '@/lib/atoms/ui';
import { useGlobalShortcuts } from '@/lib/hooks/use-global-shortcuts';

function LocationProbe() {
  const location = useLocation();
  return createElement('span', { 'data-testid': 'location' }, location.pathname);
}

function Harness() {
  useGlobalShortcuts();
  return createElement(LocationProbe);
}

function renderHarness(store: ReturnType<typeof createStore>, initialEntries = ['/board']) {
  function Wrapper({ children }: { children: ReactNode }) {
    return createElement(
      Provider,
      { store },
      createElement(MemoryRouter, { initialEntries }, children),
    );
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

  it('opens the session switcher on Cmd+K', () => {
    renderHarness(store);

    fireEvent.keyDown(document, { key: 'k', metaKey: true });
    expect(store.get(commandPaletteOpenAtom)).toBe(false);
    expect(store.get(sessionPickerOpenAtom)).toBe(true);
  });

  it('opens the session switcher on Ctrl+K', () => {
    renderHarness(store);

    fireEvent.keyDown(document, { key: 'k', ctrlKey: true });
    expect(store.get(commandPaletteOpenAtom)).toBe(false);
    expect(store.get(sessionPickerOpenAtom)).toBe(true);
  });

  it('ignores plain k with no modifier', () => {
    renderHarness(store);

    fireEvent.keyDown(document, { key: 'k' });
    expect(store.get(commandPaletteOpenAtom)).toBe(false);
  });

  it('keeps Cmd+Shift+K as a session switcher alias', () => {
    renderHarness(store);

    fireEvent.keyDown(document, { key: 'k', metaKey: true, shiftKey: true });
    expect(store.get(commandPaletteOpenAtom)).toBe(false);
    expect(store.get(sessionPickerOpenAtom)).toBe(true);
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
    expect(store.get(sessionPickerOpenAtom)).toBe(true);

    document.body.removeChild(input);
  });

  it('cleans up the listener on unmount', () => {
    const { unmount } = renderHarness(store);
    unmount();

    fireEvent.keyDown(document, { key: 'k', metaKey: true });
    expect(store.get(sessionPickerOpenAtom)).toBe(false);
  });

  it('is case-insensitive', () => {
    renderHarness(store);

    fireEvent.keyDown(document, { key: 'K', metaKey: true });
    expect(store.get(sessionPickerOpenAtom)).toBe(true);
  });

  it('opens the palette on Cmd+Shift+P', () => {
    renderHarness(store);

    fireEvent.keyDown(document, { key: 'P', metaKey: true, shiftKey: true });
    expect(store.get(commandPaletteOpenAtom)).toBe(true);
  });

  it('opens help on ?', () => {
    renderHarness(store);

    fireEvent.keyDown(document, { key: '?' });
    expect(store.get(helpOverlayOpenAtom)).toBe(true);
  });

  it('does not open help from editable targets', () => {
    renderHarness(store);

    const input = document.createElement('input');
    document.body.appendChild(input);
    input.focus();

    fireEvent.keyDown(input, { key: '?' });
    expect(store.get(helpOverlayOpenAtom)).toBe(false);

    document.body.removeChild(input);
  });

  it('Mod+. toggles the session overlay open and closed', () => {
    renderHarness(store, ['/task/task-456']);

    fireEvent.keyDown(document, { key: '.', ctrlKey: true });
    expect(store.get(sessionOverlayOpenAtom)).toBe(true);
    expect(store.get(sessionOverlayLayoutAtom)).toBe('docked');

    fireEvent.keyDown(document, { key: '.', ctrlKey: true });
    expect(store.get(sessionOverlayOpenAtom)).toBe(false);
  });

  it('accepts keyboard-code Period for the AI panel shortcut', () => {
    renderHarness(store, ['/task/task-456']);

    fireEvent.keyDown(document, { key: 'Unidentified', code: 'Period', metaKey: true });
    expect(store.get(sessionOverlayOpenAtom)).toBe(true);
    expect(store.get(sessionOverlayLayoutAtom)).toBe('docked');
  });

  it('Cmd+Shift+F toggles overlay fullscreen when the overlay is open', () => {
    store.set(sessionOverlayOpenAtom, true);
    store.set(sessionOverlayLayoutAtom, 'docked');
    renderHarness(store, ['/task/task-456']);

    fireEvent.keyDown(document, { key: 'f', metaKey: true, shiftKey: true });
    expect(store.get(sessionOverlayLayoutAtom)).toBe('fullscreen');

    fireEvent.keyDown(document, { key: 'f', metaKey: true, shiftKey: true });
    expect(store.get(sessionOverlayLayoutAtom)).toBe('docked');
  });

  it('Cmd+Shift+W toggles board and workspace routes', () => {
    const { getByTestId } = renderHarness(store, ['/board']);

    fireEvent.keyDown(document, { key: 'w', metaKey: true, shiftKey: true });
    expect(getByTestId('location').textContent).toBe('/workspace');

    fireEvent.keyDown(document, { key: 'w', metaKey: true, shiftKey: true });
    expect(getByTestId('location').textContent).toBe('/board');
  });
});
