/**
 * HelpOverlay shortcut-parity tests.
 *
 * For every global-shortcut row documented in help-overlay.tsx, this file
 * asserts that firing the documented keydown chord actually triggers the
 * expected behaviour via useGlobalShortcuts — so the docs and handlers
 * stay in sync.
 *
 * Scope: Global section rows only. Board / Task & Session rows are UI labels
 * describing feature interactions, not document-level keydown handlers, so
 * they are not tested here.
 */

import { describe, it, expect, beforeEach, vi } from 'vitest';
import { createElement, type ReactNode } from 'react';
import { createStore, Provider } from 'jotai';
import { MemoryRouter } from 'react-router';
import { fireEvent, render, screen } from '@testing-library/react';
import {
  commandPaletteOpenAtom,
  helpOverlayOpenAtom,
  rightRailModeAtom,
  rightRailTaskIdAtom,
  sessionPickerOpenAtom,
} from '@/lib/atoms/ui';
import { useGlobalShortcuts } from '@/lib/hooks/use-global-shortcuts';
import { HelpOverlay } from '@/components/layout/help-overlay';

// ── apiClient mock — useGlobalShortcuts imports it for the Cmd+. session flow ──

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    getChatSessions: vi.fn().mockResolvedValue([]),
    createChatSession: vi.fn().mockResolvedValue({ id: 'new-session' }),
  },
}));

// ── Minimal harness: mounts the global shortcuts hook in a routed context ────

function ShortcutsHarness() {
  useGlobalShortcuts();
  return null;
}

function renderHarness(
  store: ReturnType<typeof createStore>,
  initialEntries = ['/board'],
) {
  function Wrapper({ children }: { children: ReactNode }) {
    return createElement(
      Provider,
      { store },
      createElement(MemoryRouter, { initialEntries }, children),
    );
  }
  render(createElement(ShortcutsHarness), { wrapper: Wrapper });
}

// ── Tests ────────────────────────────────────────────────────────────────────

describe('HelpOverlay global shortcut parity', () => {
  let store: ReturnType<typeof createStore>;

  beforeEach(() => {
    store = createStore();
    vi.clearAllMocks();
  });

  it('does not advertise the hidden active-agent shortcut', () => {
    store.set(helpOverlayOpenAtom, true);
    render(
      createElement(
        Provider,
        { store },
        createElement(HelpOverlay),
      ),
    );

    expect(screen.queryByText('Switch active agent')).not.toBeInTheDocument();
  });

  // Row: Cmd/Ctrl + Shift + P → Open Quick Actions
  it('Cmd+Shift+P opens the command palette (Open Quick Actions row)', () => {
    renderHarness(store);
    fireEvent.keyDown(document, { key: 'P', metaKey: true, shiftKey: true });
    expect(store.get(commandPaletteOpenAtom)).toBe(true);
    expect(store.get(sessionPickerOpenAtom)).toBe(false);
  });

  it('Ctrl+Shift+P opens the command palette (Open Quick Actions row)', () => {
    renderHarness(store);
    fireEvent.keyDown(document, { key: 'P', ctrlKey: true, shiftKey: true });
    expect(store.get(commandPaletteOpenAtom)).toBe(true);
  });

  // Row: Cmd/Ctrl + K → Open Session Switcher
  it('Cmd+K opens the session switcher (Open Session Switcher row)', () => {
    renderHarness(store);
    fireEvent.keyDown(document, { key: 'k', metaKey: true });
    expect(store.get(sessionPickerOpenAtom)).toBe(true);
    expect(store.get(commandPaletteOpenAtom)).toBe(false);
  });

  it('Ctrl+K opens the session switcher (Open Session Switcher row)', () => {
    renderHarness(store);
    fireEvent.keyDown(document, { key: 'k', ctrlKey: true });
    expect(store.get(sessionPickerOpenAtom)).toBe(true);
  });

  // Row: ? / F1 → Help & Shortcuts
  it('? key opens the help overlay (Help & Shortcuts row)', () => {
    renderHarness(store);
    fireEvent.keyDown(document, { key: '?' });
    expect(store.get(helpOverlayOpenAtom)).toBe(true);
  });

  it('F1 key opens the help overlay (Help & Shortcuts row)', () => {
    renderHarness(store);
    fireEvent.keyDown(document, { key: 'F1' });
    expect(store.get(helpOverlayOpenAtom)).toBe(true);
  });

  // Row: Cmd/Ctrl + . → Cycle AI panel dock mode
  // Handler: cycles chat-right → chat-bottom → none when the rail is open.
  it('Cmd+. cycles the AI panel dock mode (Cycle AI panel dock mode row)', () => {
    // Give the rail a task context so the handler can open/cycle it.
    store.set(rightRailTaskIdAtom, 'task-xyz');
    renderHarness(store, ['/task/task-xyz']);

    // First press: opens rail in chat-right
    fireEvent.keyDown(document, { key: '.', metaKey: true });
    expect(store.get(rightRailModeAtom)).toBe('chat-right');

    // Second press: advances to chat-bottom
    fireEvent.keyDown(document, { key: '.', metaKey: true });
    expect(store.get(rightRailModeAtom)).toBe('chat-bottom');

    // Third press: closes the rail (none)
    fireEvent.keyDown(document, { key: '.', metaKey: true });
    expect(store.get(rightRailModeAtom)).toBe('none');
  });

  it('Ctrl+. cycles the AI panel dock mode (Cycle AI panel dock mode row)', () => {
    store.set(rightRailTaskIdAtom, 'task-xyz');
    renderHarness(store, ['/task/task-xyz']);

    fireEvent.keyDown(document, { key: '.', ctrlKey: true });
    expect(store.get(rightRailModeAtom)).toBe('chat-right');
  });

  // Row: Cmd/Ctrl + Shift + F → Fullscreen AI Panel
  it('Cmd+Shift+F enters fullscreen when rail is open (Fullscreen AI Panel row)', () => {
    store.set(rightRailTaskIdAtom, 'task-xyz');
    store.set(rightRailModeAtom, 'chat-right');
    renderHarness(store, ['/task/task-xyz']);

    fireEvent.keyDown(document, { key: 'f', metaKey: true, shiftKey: true });
    expect(store.get(rightRailModeAtom)).toBe('chat-fullscreen');
  });

  it('Cmd+Shift+F exits fullscreen back to docked mode (Fullscreen AI Panel row)', () => {
    store.set(rightRailTaskIdAtom, 'task-xyz');
    store.set(rightRailModeAtom, 'chat-right');
    renderHarness(store, ['/task/task-xyz']);

    // Enter fullscreen
    fireEvent.keyDown(document, { key: 'f', metaKey: true, shiftKey: true });
    expect(store.get(rightRailModeAtom)).toBe('chat-fullscreen');

    // Exit fullscreen → back to last docked mode
    fireEvent.keyDown(document, { key: 'f', metaKey: true, shiftKey: true });
    expect(store.get(rightRailModeAtom)).toBe('chat-right');
  });

  // Verify Cmd/Ctrl+Shift+P requires the Shift modifier — plain Cmd+P must NOT open the palette.
  it('Cmd+P without Shift does NOT open the command palette (shift is required)', () => {
    renderHarness(store);
    fireEvent.keyDown(document, { key: 'p', metaKey: true });
    expect(store.get(commandPaletteOpenAtom)).toBe(false);
  });

  // Verify no Ctrl+Shift+T handler exists (TUI artifact, not a web shortcut).
  it('Ctrl+Shift+T does not trigger any documented action (TUI artifact guard)', () => {
    renderHarness(store);
    const before = {
      command: store.get(commandPaletteOpenAtom),
      session: store.get(sessionPickerOpenAtom),
      help: store.get(helpOverlayOpenAtom),
      rail: store.get(rightRailModeAtom),
    };
    fireEvent.keyDown(document, { key: 't', ctrlKey: true, shiftKey: true });
    expect(store.get(commandPaletteOpenAtom)).toBe(before.command);
    expect(store.get(sessionPickerOpenAtom)).toBe(before.session);
    expect(store.get(helpOverlayOpenAtom)).toBe(before.help);
    expect(store.get(rightRailModeAtom)).toBe(before.rail);
  });
});
