/**
 * mention-link.test.tsx
 *
 * Tests:
 * - kagan#<id> calls navigate to /task/<id>
 * - #<n> renders a link to github.com/<slug>/issues/<n>
 * - Plain text is rendered as-is
 */
import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router';
import { MentionLink } from '@/components/mentions/mention-link';

const mockNavigate = vi.fn();
vi.mock('react-router', async (importOriginal) => {
  const actual = await importOriginal<typeof import('react-router')>();
  return { ...actual, useNavigate: () => mockNavigate };
});

function renderLink(text: string, slug?: string) {
  return render(
    <MemoryRouter>
      <MentionLink text={text} githubSlug={slug} />
    </MemoryRouter>,
  );
}

describe('MentionLink', () => {
  it('renders plain text unchanged', () => {
    renderLink('Hello world');
    expect(screen.getByText('Hello world')).toBeVisible();
  });

  it('renders kagan#<id> as a navigate button', async () => {
    const user = userEvent.setup();
    renderLink('See kagan#abc12345 for details');

    const btn = screen.getByRole('button', { name: /kagan#abc12345/ });
    expect(btn).toBeVisible();
    await user.click(btn);
    expect(mockNavigate).toHaveBeenCalledWith('/task/abc12345');
  });

  it('renders #<n> as an external github link', () => {
    renderLink('Related to #42', 'owner/repo');

    const link = screen.getByRole('link', { name: /#42/ });
    expect(link).toBeVisible();
    expect(link).toHaveAttribute('href', 'https://github.com/owner/repo/issues/42');
    expect(link).toHaveAttribute('target', '_blank');
  });

  it('renders #<n> with href="#" when no slug provided', () => {
    renderLink('Related to #42');

    const link = screen.getByRole('link', { name: /#42/ });
    expect(link).toHaveAttribute('href', '#');
  });

  it('handles multiple mention tokens in one string', async () => {
    const user = userEvent.setup();
    renderLink('kagan#aabbccdd and #7', 'org/repo');

    const btn = screen.getByRole('button', { name: /kagan#aabbccdd/ });
    const link = screen.getByRole('link', { name: /#7/ });
    expect(btn).toBeVisible();
    expect(link).toHaveAttribute('href', 'https://github.com/org/repo/issues/7');

    await user.click(btn);
    expect(mockNavigate).toHaveBeenCalledWith('/task/aabbccdd');
  });
});
