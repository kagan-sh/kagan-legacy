import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent, act } from '@testing-library/react';
import { createStore } from 'jotai';
import { renderWithProviders } from '@/test/render';
import { MorePopover } from './more-popover';
import { shellPopoverAtom } from '@/lib/atoms/shell';
import type { WireTask } from '@kagan/shared-api-client';

const mockTask: WireTask = {
  id: 'task-abcd-1234',
  title: 'Test task',
  status: 'IN_PROGRESS',
  priority: 'MEDIUM',
  review_running: false,
};

function openMore(store: ReturnType<typeof createStore>) {
  act(() => {
    store.set(shellPopoverAtom, { kind: 'more', anchor: { x: 200, y: 60, align: 'right' } });
  });
}

describe('MorePopover', () => {
  it('renders nothing when closed', () => {
    const store = createStore();
    renderWithProviders(<MorePopover task={mockTask} />, { store });
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('renders actions when opened', () => {
    const store = createStore();
    renderWithProviders(<MorePopover task={mockTask} />, { store });
    openMore(store);
    expect(screen.getByRole('menuitem', { name: /copy task id/i })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /open in board/i })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /advance status/i })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /delete task/i })).toBeInTheDocument();
  });

  it('calls onDelete and closes when Delete task clicked', () => {
    const onDelete = vi.fn();
    const store = createStore();
    renderWithProviders(<MorePopover task={mockTask} onDelete={onDelete} />, { store });
    openMore(store);
    fireEvent.click(screen.getByRole('menuitem', { name: /delete task/i }));
    expect(onDelete).toHaveBeenCalledWith('task-abcd-1234');
    expect(store.get(shellPopoverAtom).kind).toBeNull();
  });

  it('switches to advance popover when Advance status clicked', () => {
    const store = createStore();
    renderWithProviders(<MorePopover task={mockTask} />, { store });
    openMore(store);
    fireEvent.click(screen.getByRole('menuitem', { name: /advance status/i }));
    expect(store.get(shellPopoverAtom).kind).toBe('advance');
  });
});
