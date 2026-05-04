import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle } from '@/components/ui/empty';

describe('D9: EmptyTitle is a semantic heading', () => {
  it('renders as an <h2> element', () => {
    render(
      <Empty>
        <EmptyHeader>
          <EmptyTitle>No tasks yet</EmptyTitle>
        </EmptyHeader>
      </Empty>,
    );
    const heading = screen.getByRole('heading', { level: 2, name: 'No tasks yet' });
    expect(heading).toBeTruthy();
  });
});

describe('D9: EmptyMedia icon container is aria-hidden', () => {
  it('has aria-hidden="true" on the icon container', () => {
    const { container } = render(
      <EmptyMedia variant="icon">
        <svg aria-label="icon" />
      </EmptyMedia>,
    );
    const media = container.querySelector('[data-slot="empty-icon"]');
    expect(media).toHaveAttribute('aria-hidden', 'true');
  });
});
