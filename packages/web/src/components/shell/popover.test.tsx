import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent, act } from '@testing-library/react';
import { createStore } from 'jotai';
import { renderWithProviders } from '@/test/render';
import { PopoverPanel, PopoverTitle, PopoverItem, useShellPopover } from './popover';
import { shellPopoverAtom } from '@/lib/atoms/shell';

// A minimal wrapper that opens the 'filter' popover on mount for testing.
function TestWrapper({
  kind = 'filter' as const,
  children,
}: {
  kind?: 'filter' | 'more';
  children?: React.ReactNode;
}) {
  return (
    <>
      <PopoverPanel kind={kind}>
        <PopoverTitle>Test title</PopoverTitle>
        <PopoverItem icon="✓" label="Item one" onClick={vi.fn()} />
        {children}
      </PopoverPanel>
    </>
  );
}

function openPopover(store: ReturnType<typeof createStore>, kind: 'filter' | 'more' = 'filter') {
  act(() => {
    store.set(shellPopoverAtom, { kind, anchor: { x: 100, y: 50, align: 'left' } });
  });
}

describe('PopoverPanel', () => {
  it('does not render when atom kind is null', () => {
    const store = createStore();
    renderWithProviders(<TestWrapper />, { store });
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('renders when atom opens matching kind', () => {
    const store = createStore();
    renderWithProviders(<TestWrapper />, { store });
    openPopover(store);
    expect(screen.getByRole('menu')).toBeInTheDocument();
    expect(screen.getByText('Test title')).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: /item one/i })).toBeInTheDocument();
  });

  it('closes on Escape key', () => {
    const store = createStore();
    renderWithProviders(<TestWrapper />, { store });
    openPopover(store);
    expect(screen.getByRole('menu')).toBeInTheDocument();
    fireEvent.keyDown(document, { key: 'Escape' });
    expect(screen.queryByRole('menu')).toBeNull();
    expect(store.get(shellPopoverAtom).kind).toBeNull();
  });

  it('closes on outside click', () => {
    const store = createStore();
    const { baseElement } = renderWithProviders(<TestWrapper />, { store });
    openPopover(store);
    expect(screen.getByRole('menu')).toBeInTheDocument();
    // Click outside the popover
    fireEvent.mouseDown(baseElement);
    expect(screen.queryByRole('menu')).toBeNull();
  });

  it('does not close when clicking inside popover', () => {
    const store = createStore();
    renderWithProviders(<TestWrapper />, { store });
    openPopover(store);
    const menu = screen.getByRole('menu');
    fireEvent.mouseDown(menu);
    expect(screen.queryByRole('menu')).toBeInTheDocument();
  });

  it('closes when a different popover kind is set', () => {
    const store = createStore();
    renderWithProviders(<TestWrapper kind="filter" />, { store });
    openPopover(store, 'filter');
    expect(screen.getByRole('menu')).toBeInTheDocument();
    act(() => {
      store.set(shellPopoverAtom, { kind: 'more', anchor: { x: 0, y: 0, align: 'left' } });
    });
    // 'filter' panel should no longer render
    expect(screen.queryByRole('menu')).toBeNull();
  });
});

describe('useShellPopover', () => {
  function HookHost({ kind = 'filter' as const }: { kind?: 'filter' }) {
    const { isOpen, openFromEvent, close } = useShellPopover(kind);
    return (
      <div>
        <span data-testid="state">{isOpen ? 'open' : 'closed'}</span>
        <button
          type="button"
          data-testid="trigger"
          onClick={(e) => openFromEvent(e)}
        >
          open
        </button>
        <button type="button" data-testid="closer" onClick={close}>
          close
        </button>
      </div>
    );
  }

  it('reflects open/closed state', () => {
    const store = createStore();
    renderWithProviders(<HookHost />, { store });
    expect(screen.getByTestId('state')).toHaveTextContent('closed');
    fireEvent.click(screen.getByTestId('trigger'));
    expect(screen.getByTestId('state')).toHaveTextContent('open');
    fireEvent.click(screen.getByTestId('closer'));
    expect(screen.getByTestId('state')).toHaveTextContent('closed');
  });

  it('toggles when trigger is clicked twice', () => {
    const store = createStore();
    renderWithProviders(<HookHost />, { store });
    fireEvent.click(screen.getByTestId('trigger'));
    expect(screen.getByTestId('state')).toHaveTextContent('open');
    fireEvent.click(screen.getByTestId('trigger'));
    expect(screen.getByTestId('state')).toHaveTextContent('closed');
  });
});
