import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '@/test/render';
import { StatusBadge } from '@/components/shared/status-badge';

describe('StatusBadge', () => {
  it('renders correct label for BACKLOG', () => {
    renderWithProviders(<StatusBadge status="BACKLOG" />);
    expect(screen.getByText('Backlog')).toBeVisible();
  });

  it('renders correct label for IN_PROGRESS', () => {
    renderWithProviders(<StatusBadge status="IN_PROGRESS" />);
    expect(screen.getByText('In Progress')).toBeVisible();
  });
});
