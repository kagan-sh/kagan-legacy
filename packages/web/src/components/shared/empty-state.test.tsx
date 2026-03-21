import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '@/test/render';
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription, EmptyContent } from '@/components/ui/empty';

describe('Empty (shadcn)', () => {
  it('renders title and description', () => {
    renderWithProviders(
      <Empty>
        <EmptyHeader>
          <EmptyTitle>No tasks</EmptyTitle>
          <EmptyDescription>Create a new task to get started</EmptyDescription>
        </EmptyHeader>
      </Empty>,
    );
    expect(screen.getByText('No tasks')).toBeVisible();
    expect(screen.getByText('Create a new task to get started')).toBeVisible();
  });

  it('renders action button when provided', () => {
    renderWithProviders(
      <Empty>
        <EmptyHeader>
          <EmptyTitle>Empty</EmptyTitle>
        </EmptyHeader>
        <EmptyContent>
          <button>Add</button>
        </EmptyContent>
      </Empty>,
    );
    expect(screen.getByText('Add')).toBeVisible();
  });

  it('renders icon via EmptyMedia', () => {
    renderWithProviders(
      <Empty>
        <EmptyHeader>
          <EmptyMedia variant="icon">
            <svg data-testid="test-icon" />
          </EmptyMedia>
          <EmptyTitle>With icon</EmptyTitle>
        </EmptyHeader>
      </Empty>,
    );
    expect(screen.getByTestId('test-icon')).toBeVisible();
    expect(screen.getByText('With icon')).toBeVisible();
  });
});
