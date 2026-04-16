import { describe, expect, it } from 'vitest';
import { screen } from '@testing-library/react';
import { ActivityBar } from '@/components/layout/activity-bar';
import { renderWithProviders } from '@/test/render';

describe('ActivityBar', () => {
  it('renders core navigation links', () => {
    renderWithProviders(<ActivityBar />);

    expect(screen.getByRole('link', { name: /^Home/ })).toBeVisible();
    expect(screen.getByRole('link', { name: /^Board/ })).toBeVisible();
    expect(screen.getByRole('link', { name: /^Workspace/ })).toBeVisible();
    expect(screen.getByRole('link', { name: /^Settings/ })).toBeVisible();
  });

  it('marks the current route as active', () => {
    renderWithProviders(<ActivityBar />, { initialEntries: ['/settings'] });

    expect(screen.getByRole('link', { name: /^Settings/ })).toHaveAttribute('aria-current', 'page');
  });
});
