import { describe, expect, it, beforeEach, vi } from 'vitest';
import { screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { createRef } from 'react';
import { renderWithProviders } from '@/test/render';
import { ChatView } from '@/components/chat/chat-view';

describe('ChatView', () => {
  beforeEach(() => {
    localStorage.clear();
  });

  it('scopes input history to the loaded session project', async () => {
    const user = userEvent.setup();
    localStorage.setItem('kagan:chat-history:project-1', JSON.stringify(['project note']));

    renderWithProviders(
      <ChatView
        sessionId="session-1"
        projectId="project-1"
        messages={[]}
        streamEntries={[]}
        isStreaming={false}
        onPrefillConsumed={vi.fn()}
        onSend={vi.fn()}
        onInterrupt={vi.fn()}
        onSlashCommand={vi.fn()}
        scrollRef={createRef<HTMLDivElement>()}
      />,
    );

    const input = screen.getByPlaceholderText('Type a message or / for commands...');
    await user.click(input);
    await user.keyboard('{ArrowUp}');

    expect(input).toHaveValue('project note');
  });
});
