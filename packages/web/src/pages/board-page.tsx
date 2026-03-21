import { KanbanBoard } from '@/components/board/kanban-board';
import { ErrorBoundary } from '@/components/shared/error-boundary';

function BoardPage() {
  return (
    <ErrorBoundary>
      <KanbanBoard />
    </ErrorBoundary>
  );
}

export const Component = BoardPage;
