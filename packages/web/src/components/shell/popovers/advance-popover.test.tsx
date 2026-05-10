import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, fireEvent, act } from '@testing-library/react';
import { createStore } from 'jotai';
import { renderWithProviders } from '@/test/render';
import { AdvancePopover } from './advance-popover';
import { shellPopoverAtom } from '@/lib/atoms/shell';
import { apiClient } from '@/lib/api/client';

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    transitionStatus: vi.fn(),
  },
}));

function openAdvance(store: ReturnType<typeof createStore>) {
  act(() => {
    store.set(shellPopoverAtom, { kind: 'advance', anchor: { x: 200, y: 60, align: 'right' } });
  });
}

describe('AdvancePopover', () => {
  beforeEach(() => {
    vi.mocked(apiClient.transitionStatus).mockResolvedValue({
      id: 'task-1',
      title: 'Test',
      status: 'REVIEW',
      priority: 'MEDIUM',
      review_running: false,
    });
  });

  it('renders nothing when closed', () => {
    const store = createStore();
    renderWithProviders(<AdvancePopover taskId="task-1" currentStatus="IN_PROGRESS" />, { store });
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('renders canonical status labels', () => {
    const store = createStore();
    renderWithProviders(<AdvancePopover taskId="task-1" currentStatus="IN_PROGRESS" />, { store });
    openAdvance(store);
    // Must show canonical labels — never "RUN"
    expect(screen.getByRole('menuitem', { name: /^Backlog/i })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /^In Progress/i })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /^Review/i })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /^Done/i })).toBeInTheDocument();
    expect(screen.queryByText(/\bRUN\b/)).toBeNull();
  });

  it('calls transitionStatus and fires onTransitioned when an item is selected', async () => {
    const onTransitioned = vi.fn();
    const store = createStore();
    renderWithProviders(
      <AdvancePopover taskId="task-1" currentStatus="IN_PROGRESS" onTransitioned={onTransitioned} />,
      { store },
    );
    openAdvance(store);
    fireEvent.click(screen.getByRole('menuitem', { name: /^Review/i }));
    await vi.waitFor(() => {
      expect(apiClient.transitionStatus).toHaveBeenCalledWith('task-1', 'REVIEW');
      expect(onTransitioned).toHaveBeenCalledWith('task-1', 'REVIEW');
    });
    expect(store.get(shellPopoverAtom).kind).toBeNull();
  });

  it('marks current status as active', () => {
    const store = createStore();
    renderWithProviders(<AdvancePopover taskId="task-1" currentStatus="REVIEW" />, { store });
    openAdvance(store);
    const reviewBtn = screen.getByRole('menuitem', { name: /^Review/i });
    expect(reviewBtn).toHaveAttribute('data-active', 'true');
    const backlogBtn = screen.getByRole('menuitem', { name: /^Backlog/i });
    expect(backlogBtn).toHaveAttribute('data-active', 'false');
  });
});
