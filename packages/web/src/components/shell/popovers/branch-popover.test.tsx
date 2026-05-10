import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, act, fireEvent } from '@testing-library/react';
import { createStore } from 'jotai';
import { renderWithProviders } from '@/test/render';
import { BranchPopover } from './branch-popover';
import { shellPopoverAtom, composerBranchAtom } from '@/lib/atoms/shell';
import { tasksAtom } from '@/lib/atoms/board';

// Stub navigator.clipboard
const writeTextMock = vi.fn().mockResolvedValue(undefined);
Object.defineProperty(navigator, 'clipboard', {
  value: { writeText: writeTextMock },
  writable: true,
  configurable: true,
});

function openBranch(store: ReturnType<typeof createStore>) {
  act(() => {
    store.set(shellPopoverAtom, {
      kind: 'branch',
      anchor: { x: 100, y: 50, align: 'left' },
    });
  });
}

describe('BranchPopover', () => {
  beforeEach(() => {
    writeTextMock.mockClear();
  });

  it('renders nothing when closed', () => {
    const store = createStore();
    renderWithProviders(<BranchPopover />, { store });
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('renders at least the main branch when opened', () => {
    const store = createStore();
    renderWithProviders(<BranchPopover />, { store });
    openBranch(store);
    expect(screen.getByRole('menu')).toBeInTheDocument();
    expect(screen.getByText('main')).toBeInTheDocument();
  });

  it('lists branches from in-progress tasks', () => {
    const store = createStore();
    store.set(tasksAtom, [
      {
        id: 't1',
        title: 'Task 1',
        status: 'IN_PROGRESS',
        priority: 'MEDIUM',
        base_branch: 'feat/api-refactor',
      },
      {
        id: 't2',
        title: 'Task 2',
        status: 'REVIEW',
        priority: 'HIGH',
        base_branch: 'feat/ui-polish',
      },
    ] as never);

    renderWithProviders(<BranchPopover />, { store });
    openBranch(store);

    expect(screen.getByText('feat/api-refactor')).toBeInTheDocument();
    expect(screen.getByText('feat/ui-polish')).toBeInTheDocument();
  });

  it('does not duplicate branches from multiple tasks sharing same branch', () => {
    const store = createStore();
    store.set(tasksAtom, [
      { id: 't1', title: 'T1', status: 'IN_PROGRESS', priority: 'MEDIUM', base_branch: 'main' },
      { id: 't2', title: 'T2', status: 'REVIEW', priority: 'MEDIUM', base_branch: 'main' },
    ] as never);

    renderWithProviders(<BranchPopover />, { store });
    openBranch(store);

    const mainItems = screen.getAllByText('main');
    expect(mainItems).toHaveLength(1);
  });

  it('clicking a branch sets composerBranchAtom and closes popover', () => {
    const store = createStore();
    store.set(tasksAtom, [
      { id: 't1', title: 'T1', status: 'IN_PROGRESS', priority: 'MEDIUM', base_branch: 'feat/branch-a' },
    ] as never);

    renderWithProviders(<BranchPopover />, { store });
    openBranch(store);

    fireEvent.click(screen.getByText('feat/branch-a'));

    expect(store.get(composerBranchAtom)).toBe('feat/branch-a');
    expect(store.get(shellPopoverAtom).kind).toBeNull();
  });

  it('clicking main sets composerBranchAtom to main and closes', () => {
    const store = createStore();
    renderWithProviders(<BranchPopover />, { store });
    openBranch(store);

    fireEvent.click(screen.getByText('main'));

    expect(store.get(composerBranchAtom)).toBe('main');
    expect(store.get(shellPopoverAtom).kind).toBeNull();
  });

  it('copy button writes the selected branch label to clipboard', async () => {
    const store = createStore();
    store.set(composerBranchAtom, 'feat/selected');
    renderWithProviders(<BranchPopover />, { store });
    openBranch(store);

    fireEvent.click(screen.getByTestId('branch-popover-copy-btn'));

    await vi.waitFor(() => {
      expect(writeTextMock).toHaveBeenCalledWith('feat/selected');
    });
  });

  it('copy button defaults to main when no branch is selected', async () => {
    const store = createStore();
    renderWithProviders(<BranchPopover />, { store });
    openBranch(store);

    fireEvent.click(screen.getByTestId('branch-popover-copy-btn'));

    await vi.waitFor(() => {
      expect(writeTextMock).toHaveBeenCalledWith('main');
    });
  });

  it('marks the selected branch as active', () => {
    const store = createStore();
    store.set(composerBranchAtom, 'main');
    store.set(tasksAtom, [
      { id: 't1', title: 'T1', status: 'IN_PROGRESS', priority: 'MEDIUM', base_branch: 'feat/other' },
    ] as never);

    renderWithProviders(<BranchPopover />, { store });
    openBranch(store);

    const mainBtn = screen.getByRole('menuitem', { name: /^main/i });
    expect(mainBtn).toHaveAttribute('data-active', 'true');

    const otherBtn = screen.getByRole('menuitem', { name: /^feat\/other/i });
    expect(otherBtn).toHaveAttribute('data-active', 'false');
  });

  it('closes on Escape', () => {
    const store = createStore();
    renderWithProviders(<BranchPopover />, { store });
    openBranch(store);

    expect(screen.getByRole('menu')).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(store.get(shellPopoverAtom).kind).toBeNull();
  });
});
