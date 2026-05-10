import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { createStore } from 'jotai';
import { renderWithProviders } from '@/test/render';
import { BoardToolbar, KbHintFooter } from '@/components/board/board-toolbar';
import { boardViewModeAtom } from '@/lib/atoms/shell';
import { mockProject } from '@/test/mocks';

describe('BoardToolbar', () => {
  it('shows project name in breadcrumb', () => {
    const store = createStore();
    renderWithProviders(
      <BoardToolbar
        project={mockProject({ name: 'kagan' })}
        totalTasks={7}
        view="board"
        setView={vi.fn()}
        onCreateTask={vi.fn()}
      />,
      { store },
    );
    expect(screen.getByTestId('crumb-project')).toHaveTextContent('kagan');
  });

  it('shows total tasks count in breadcrumb', () => {
    renderWithProviders(
      <BoardToolbar
        project={null}
        totalTasks={12}
        view="board"
        setView={vi.fn()}
        onCreateTask={vi.fn()}
      />,
    );
    expect(screen.getByTestId('crumb-total')).toHaveTextContent('12 tasks');
  });

  it('falls back to "Workspace" when project is null', () => {
    renderWithProviders(
      <BoardToolbar
        project={null}
        totalTasks={0}
        view="board"
        setView={vi.fn()}
        onCreateTask={vi.fn()}
      />,
    );
    expect(screen.getByTestId('crumb-project')).toHaveTextContent('Workspace');
  });

  it('marks the active view mode button with aria-current', () => {
    renderWithProviders(
      <BoardToolbar
        project={null}
        totalTasks={0}
        view="list"
        setView={vi.fn()}
        onCreateTask={vi.fn()}
      />,
    );
    const listBtn = screen.getByTestId('view-mode-list');
    const boardBtn = screen.getByTestId('view-mode-board');
    expect(listBtn).toHaveAttribute('aria-current', 'true');
    expect(boardBtn).not.toHaveAttribute('aria-current');
  });

  it('calls setView with "list" when List button is clicked', () => {
    const setView = vi.fn();
    renderWithProviders(
      <BoardToolbar
        project={null}
        totalTasks={0}
        view="board"
        setView={setView}
        onCreateTask={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId('view-mode-list'));
    expect(setView).toHaveBeenCalledWith('list');
  });

  it('calls setView with "board" when Board button is clicked', () => {
    const setView = vi.fn();
    renderWithProviders(
      <BoardToolbar
        project={null}
        totalTasks={0}
        view="list"
        setView={setView}
        onCreateTask={vi.fn()}
      />,
    );
    fireEvent.click(screen.getByTestId('view-mode-board'));
    expect(setView).toHaveBeenCalledWith('board');
  });

  it('Board/List toggle persists to boardViewModeAtom when wired through atom', () => {
    const store = createStore();
    store.set(boardViewModeAtom, 'board');

    const TestWrapper = () => {
      const [view, setView] = [store.get(boardViewModeAtom), (v: 'board' | 'list') => store.set(boardViewModeAtom, v)];
      return (
        <BoardToolbar
          project={null}
          totalTasks={0}
          view={view}
          setView={setView}
          onCreateTask={vi.fn()}
        />
      );
    };

    renderWithProviders(<TestWrapper />, { store });
    fireEvent.click(screen.getByTestId('view-mode-list'));
    expect(store.get(boardViewModeAtom)).toBe('list');
  });

  it('calls onCreateTask when New task button clicked', () => {
    const onCreateTask = vi.fn();
    renderWithProviders(
      <BoardToolbar
        project={null}
        totalTasks={0}
        view="board"
        setView={vi.fn()}
        onCreateTask={onCreateTask}
      />,
    );
    fireEvent.click(screen.getByRole('button', { name: /create new task/i }));
    expect(onCreateTask).toHaveBeenCalled();
  });
});

describe('KbHintFooter', () => {
  it('shows the running count', () => {
    renderWithProviders(<KbHintFooter runningCount={3} />);
    expect(screen.getByTestId('hint-running')).toHaveTextContent('3 running');
  });

  it('shows zero running when no tasks are running', () => {
    renderWithProviders(<KbHintFooter runningCount={0} />);
    expect(screen.getByTestId('hint-running')).toHaveTextContent('0 running');
  });
});
