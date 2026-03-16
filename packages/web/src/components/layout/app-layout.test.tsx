import { describe, expect, it, vi } from 'vitest';
import { createStore } from 'jotai';
import { fireEvent, screen, within } from '@testing-library/react';
import { renderWithProviders } from '@/test/render';
import { Component as AppLayout } from '@/components/layout/app-layout';
import {
  commandPaletteOpenAtom,
  rightRailModeAtom,
  rightRailTaskIdAtom,
  sessionPickerOpenAtom,
} from '@/lib/atoms/ui';

vi.mock('@/lib/hooks/use-websocket-sync', () => ({
  useWebSocketSync: () => undefined,
}));

vi.mock('@/lib/hooks/use-mobile', () => ({
  useIsMobile: () => false,
}));

vi.mock('@/components/session/chat-side-panel', () => ({
  ChatSidePanel: ({
    taskId,
    layout,
    onClose,
  }: {
    taskId: string;
    layout: string;
    onClose: () => void;
  }) => (
    <div data-testid="chat-side-panel" data-layout={layout}>
      <span>{taskId}</span>
      <button type="button" onClick={onClose}>Close chat</button>
    </div>
  ),
}));

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    getProjects: vi.fn().mockResolvedValue([{ id: '1', name: 'Test', active: true }]),
  },
}));

describe('AppLayout', () => {
  it('renders Quick Actions when commandPaletteOpenAtom is true', async () => {
    const store = createStore();
    store.set(commandPaletteOpenAtom, true);

    renderWithProviders(<AppLayout />, { store, initialEntries: ['/board'] });

    const dialog = await screen.findByRole('dialog', { name: 'Quick Actions' });
    expect(within(dialog).getByRole('combobox')).toBeVisible();
    expect(within(dialog).getByRole('option', { name: /^Board/ })).toBeVisible();
    expect(within(dialog).getByRole('option', { name: /^Settings/ })).toBeVisible();
    expect(within(dialog).getByRole('option', { name: /^Session Switcher/ })).toBeVisible();
  });

  it('cycles chat rail with Space and closes, Mod+I toggles AI panel', async () => {
    const store = createStore();
    store.set(rightRailModeAtom, 'chat-right');
    store.set(rightRailTaskIdAtom, 'task-123');

    renderWithProviders(<AppLayout />, { store, initialEntries: ['/task/task-123'] });

    expect(await screen.findByTestId('chat-side-panel')).toHaveAttribute('data-layout', 'chat-right');

    fireEvent.keyDown(window, { key: ' ' });
    expect(store.get(rightRailModeAtom)).toBe('chat-bottom');

    fireEvent.keyDown(window, { key: 'Escape' });
    expect(store.get(rightRailModeAtom)).toBe('none');
  });

  it('Mod+I cycles chat-right → chat-bottom → closed (no fullscreen)', async () => {
    const store = createStore();
    store.set(rightRailTaskIdAtom, 'task-456');

    renderWithProviders(<AppLayout />, { store, initialEntries: ['/task/task-456'] });

    // Mod+I when closed → open chat-right
    fireEvent.keyDown(window, { key: 'i', ctrlKey: true });
    expect(store.get(rightRailModeAtom)).toBe('chat-right');

    // Mod+I when chat-right → switch to chat-bottom
    fireEvent.keyDown(window, { key: 'i', ctrlKey: true });
    expect(store.get(rightRailModeAtom)).toBe('chat-bottom');

    // Mod+I when chat-bottom → close
    fireEvent.keyDown(window, { key: 'i', ctrlKey: true });
    expect(store.get(rightRailModeAtom)).toBe('none');
  });

  it('uses canonical global shortcuts and disables removed legacy aliases', async () => {
    const store = createStore();
    renderWithProviders(<AppLayout />, { store, initialEntries: ['/board'] });

    fireEvent.keyDown(window, { key: 'P', ctrlKey: true, shiftKey: true });
    expect(store.get(commandPaletteOpenAtom)).toBe(true);

    store.set(commandPaletteOpenAtom, false);
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true, shiftKey: true });
    expect(store.get(sessionPickerOpenAtom)).toBe(true);

    store.set(sessionPickerOpenAtom, false);
    fireEvent.keyDown(window, { key: 'k', ctrlKey: true });
    expect(store.get(sessionPickerOpenAtom)).toBe(false);
  });
});
