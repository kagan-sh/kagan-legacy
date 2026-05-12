import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '@/test/render';
import { MobileTabs } from './mobile-tabs';

describe('MobileTabs', () => {
  it('renders all three tabs', () => {
    renderWithProviders(<MobileTabs />);
    expect(screen.getByRole('link', { name: /workspace/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /kanban/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /settings/i })).toBeInTheDocument();
  });

  it('marks the Kanban tab aria-current="page" on /board', () => {
    renderWithProviders(<MobileTabs />, { initialEntries: ['/board'] });
    expect(screen.getByRole('link', { name: /kanban/i })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: /workspace/i })).not.toHaveAttribute('aria-current');
    expect(screen.getByRole('link', { name: /settings/i })).not.toHaveAttribute('aria-current');
  });

  it('marks the Workspace tab aria-current="page" on /chat', () => {
    renderWithProviders(<MobileTabs />, { initialEntries: ['/chat'] });
    expect(screen.getByRole('link', { name: /workspace/i })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: /kanban/i })).not.toHaveAttribute('aria-current');
    expect(screen.getByRole('link', { name: /settings/i })).not.toHaveAttribute('aria-current');
  });

  it('marks the Settings tab aria-current="page" on /settings', () => {
    renderWithProviders(<MobileTabs />, { initialEntries: ['/settings'] });
    expect(screen.getByRole('link', { name: /settings/i })).toHaveAttribute('aria-current', 'page');
    expect(screen.getByRole('link', { name: /workspace/i })).not.toHaveAttribute('aria-current');
    expect(screen.getByRole('link', { name: /kanban/i })).not.toHaveAttribute('aria-current');
  });

  it('defaults Workspace as active on the root path', () => {
    renderWithProviders(<MobileTabs />, { initialEntries: ['/'] });
    expect(screen.getByRole('link', { name: /workspace/i })).toHaveAttribute('aria-current', 'page');
  });

  it('marks Kanban active on /task/:id routes', () => {
    renderWithProviders(<MobileTabs />, { initialEntries: ['/task/abc123'] });
    expect(screen.getByRole('link', { name: /kanban/i })).toHaveAttribute('aria-current', 'page');
  });

  it('has the correct accessible nav label', () => {
    renderWithProviders(<MobileTabs />);
    expect(screen.getByRole('navigation', { name: /mobile tabs/i })).toBeInTheDocument();
  });
});
