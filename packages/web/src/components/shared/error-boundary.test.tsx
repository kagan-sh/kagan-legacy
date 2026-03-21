import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '@/test/render';
import { ErrorBoundary } from '@/components/shared/error-boundary';

function ThrowingChild(): never {
  throw new Error('Test error');
}

describe('ErrorBoundary', () => {
  it('renders children when no error', () => {
    renderWithProviders(
      <ErrorBoundary>
        <div>Hello</div>
      </ErrorBoundary>,
    );
    expect(screen.getByText('Hello')).toBeVisible();
  });

  it('shows fallback on error', () => {
    // Suppress console.error from ErrorBoundary
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {});
    renderWithProviders(
      <ErrorBoundary>
        <ThrowingChild />
      </ErrorBoundary>,
    );
    expect(screen.getByText('Something went wrong')).toBeVisible();
    expect(screen.getByText('Test error')).toBeVisible();
    spy.mockRestore();
  });
});
