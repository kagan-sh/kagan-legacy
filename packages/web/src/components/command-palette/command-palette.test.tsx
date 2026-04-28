import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { createStore } from 'jotai';
import { screen, waitFor, within } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/render';
import { CommandPalette } from '@/components/command-palette/command-palette';
import { commandPaletteOpenAtom } from '@/lib/atoms/ui';
import {
  __resetRegistryForTests,
  registerCommand,
} from '@/lib/commands/registry';
import { __resetBuiltinRegistrationForTests } from '@/lib/commands/commands';

function openPalette(store: ReturnType<typeof createStore>) {
  store.set(commandPaletteOpenAtom, true);
}

describe('CommandPalette', () => {
  beforeEach(() => {
    __resetRegistryForTests();
    __resetBuiltinRegistrationForTests();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('is hidden when the open atom is false', () => {
    const store = createStore();
    renderWithProviders(<CommandPalette />, { store });
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('renders built-in navigation commands when opened', async () => {
    const store = createStore();
    openPalette(store);

    renderWithProviders(<CommandPalette />, { store });

    const dialog = await screen.findByRole('dialog', { name: /command palette/i });
    expect(within(dialog).getByRole('option', { name: /Go to Board/i })).toBeVisible();
    expect(within(dialog).getByRole('option', { name: /Go to Analytics/i })).toBeVisible();
    expect(within(dialog).getByRole('option', { name: /Go to Settings/i })).toBeVisible();
    expect(within(dialog).getByRole('option', { name: /Create task/i })).toBeVisible();
  });

  it('labels the input as the command palette', async () => {
    const store = createStore();
    openPalette(store);

    renderWithProviders(<CommandPalette />, { store });

    const input = await screen.findByRole('combobox');
    expect(input).toHaveAttribute('aria-label', 'Command palette');
    expect(input).toHaveAttribute('placeholder', expect.stringContaining('Type a command'));
  });

  it('fuzzy-matches via keywords (e.g. "new" finds "Create task")', async () => {
    const store = createStore();
    openPalette(store);

    renderWithProviders(<CommandPalette />, { store });

    const input = await screen.findByRole('combobox');
    const user = userEvent.setup();
    await user.type(input, 'new');

    await waitFor(() => {
      expect(screen.getByRole('option', { name: /Create task/i })).toBeVisible();
    });
    expect(screen.queryByRole('option', { name: /Go to Analytics/i })).not.toBeInTheDocument();
  });

  it('shows the empty state when no commands match', async () => {
    const store = createStore();
    openPalette(store);

    renderWithProviders(<CommandPalette />, { store });

    const input = await screen.findByRole('combobox');
    const user = userEvent.setup();
    await user.type(input, 'zzzzzzzzzzzzz');

    expect(await screen.findByText(/No commands match/i)).toBeVisible();
  });

  it('executes a custom command handler and closes on selection', async () => {
    const handler = vi.fn();
    registerCommand({
      id: 'custom-test',
      title: 'My custom command',
      section: 'Navigate',
      handler,
    });

    const store = createStore();
    openPalette(store);

    renderWithProviders(<CommandPalette />, { store });

    const option = await screen.findByRole('option', { name: /My custom command/i });
    const user = userEvent.setup();
    await user.click(option);

    expect(handler).toHaveBeenCalledTimes(1);
    await waitFor(() => {
      expect(store.get(commandPaletteOpenAtom)).toBe(false);
    });
  });

  it('invokes the onCommandExecute telemetry hook', async () => {
    const onCommandExecute = vi.fn();
    registerCommand({
      id: 'telemetry-test',
      title: 'Telemetry target',
      section: 'Navigate',
      handler: vi.fn(),
    });

    const store = createStore();
    openPalette(store);

    renderWithProviders(<CommandPalette onCommandExecute={onCommandExecute} />, { store });

    const option = await screen.findByRole('option', { name: /Telemetry target/i });
    const user = userEvent.setup();
    await user.click(option);

    expect(onCommandExecute).toHaveBeenCalledTimes(1);
    expect(onCommandExecute.mock.calls[0]![0].id).toBe('telemetry-test');
  });

  it('defaults the telemetry hook to console.debug', async () => {
    const debugSpy = vi.spyOn(console, 'debug').mockImplementation(() => {});
    registerCommand({
      id: 'default-telemetry',
      title: 'Default telemetry',
      section: 'Navigate',
      handler: vi.fn(),
    });

    const store = createStore();
    openPalette(store);

    renderWithProviders(<CommandPalette />, { store });

    const option = await screen.findByRole('option', { name: /Default telemetry/i });
    const user = userEvent.setup();
    await user.click(option);

    expect(debugSpy).toHaveBeenCalledWith(
      '[command-palette]',
      'default-telemetry',
    );
  });

  it('hides commands whose when() guard returns false', async () => {
    registerCommand({
      id: 'guarded-off',
      title: 'Guarded off',
      section: 'Navigate',
      when: () => false,
      handler: vi.fn(),
    });
    registerCommand({
      id: 'guarded-on',
      title: 'Guarded on',
      section: 'Navigate',
      when: () => true,
      handler: vi.fn(),
    });

    const store = createStore();
    openPalette(store);

    renderWithProviders(<CommandPalette />, { store });

    expect(await screen.findByRole('option', { name: /Guarded on/i })).toBeVisible();
    expect(screen.queryByRole('option', { name: /Guarded off/i })).not.toBeInTheDocument();
  });

  it('closes on Escape', async () => {
    const store = createStore();
    openPalette(store);

    renderWithProviders(<CommandPalette />, { store });

    await screen.findByRole('dialog', { name: /command palette/i });
    const user = userEvent.setup();
    await user.keyboard('{Escape}');

    await waitFor(() => {
      expect(store.get(commandPaletteOpenAtom)).toBe(false);
    });
  });

  it('renders the footer with keyboard hints', async () => {
    const store = createStore();
    openPalette(store);

    renderWithProviders(<CommandPalette />, { store });

    await screen.findByRole('dialog', { name: /command palette/i });
    expect(screen.getByText('navigate')).toBeVisible();
    expect(screen.getByText('select')).toBeVisible();
    expect(screen.getByText('close')).toBeVisible();
  });
});
