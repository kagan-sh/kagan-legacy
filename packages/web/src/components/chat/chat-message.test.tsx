import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { renderWithProviders } from '@/test/render';
import { ChatMessage } from '@/components/chat/chat-message';

describe('ChatMessage', () => {
  it('strips script tags from assistant markdown output', () => {
    const { container } = renderWithProviders(
      <ChatMessage message={{ role: 'assistant', content: '<script>alert(1)</script>safe text' }} />,
    );

    expect(container.querySelector('script')).toBeNull();
    expect(screen.getByText('safe text')).toBeVisible();
  });

  it('renders user and assistant roles with correct labels', () => {
    renderWithProviders(
      <ChatMessage message={{ role: 'user', content: 'plain user text' }} />,
    );
    expect(screen.getByText('plain user text')).toBeVisible();
    expect(screen.getByText('You')).toBeVisible();

    renderWithProviders(
      <ChatMessage message={{ role: 'assistant', content: '**assistant text**' }} />,
    );
    expect(screen.getByText('assistant text')).toBeVisible();
    expect(screen.getByText('Agent')).toBeVisible();
  });

  it('sets data-role attribute for styling hooks', () => {
    const { container } = renderWithProviders(
      <ChatMessage message={{ role: 'user', content: 'test' }} />,
    );
    expect(container.querySelector('[data-role="user"]')).not.toBeNull();
  });
});
