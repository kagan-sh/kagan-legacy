import { describe, it, expect, vi } from 'vitest';
import { fireEvent, screen } from '@testing-library/react';
import { createStore } from 'jotai';
import { renderWithProviders } from '@/test/render';
import { ChatInputBar } from './chat-input-bar';
import { shellPopoverAtom, currentAgentCliAtom } from '@/lib/atoms/shell';

const noop = () => {};

describe('ChatInputBar chip row', () => {
  it('renders attach button, agent CLI chip, voice button, and send button', () => {
    renderWithProviders(<ChatInputBar onSend={noop} />);
    expect(screen.getByTestId('composer-attach-btn')).toBeInTheDocument();
    expect(screen.getByTestId('composer-agent-cli-chip')).toBeInTheDocument();
    expect(screen.getByTestId('composer-voice-btn')).toBeInTheDocument();
    expect(screen.getByTestId('composer-send-btn')).toBeInTheDocument();
  });

  it('does not render the dropped chips (locality / permissions / branch)', () => {
    renderWithProviders(<ChatInputBar onSend={noop} />);
    expect(screen.queryByTestId('composer-locality-chip')).toBeNull();
    expect(screen.queryByTestId('composer-permissions-chip')).toBeNull();
    expect(screen.queryByTestId('composer-branch-chip')).toBeNull();
    expect(screen.queryByTestId('composer-model-chip')).toBeNull();
  });

  it('send button is disabled when input is empty', () => {
    renderWithProviders(<ChatInputBar onSend={noop} />);
    expect(screen.getByTestId('composer-send-btn')).toBeDisabled();
  });

  it('send button is enabled after typing', () => {
    renderWithProviders(<ChatInputBar onSend={noop} />);
    const textarea = screen.getByTestId('chat-composer-input');
    fireEvent.change(textarea, { target: { value: 'hello' } });
    expect(screen.getByTestId('composer-send-btn')).not.toBeDisabled();
  });

  it('agent-cli chip opens agent-cli popover via shellPopoverAtom', () => {
    const store = createStore();
    renderWithProviders(<ChatInputBar onSend={noop} />, { store });

    fireEvent.click(screen.getByTestId('composer-agent-cli-chip'));

    const popover = store.get(shellPopoverAtom);
    expect(popover.kind).toBe('agent-cli');
  });

  it('agent-cli chip label reflects currentAgentCliAtom', () => {
    const store = createStore();
    store.set(currentAgentCliAtom, 'claude-code');
    renderWithProviders(<ChatInputBar onSend={noop} />, { store });
    expect(screen.getByTestId('composer-agent-cli-chip')).toHaveTextContent('claude-code');
  });

  it('agent-cli chip falls back to "Agent CLI" when atom is null', () => {
    renderWithProviders(<ChatInputBar onSend={noop} />);
    expect(screen.getByTestId('composer-agent-cli-chip')).toHaveTextContent('Agent CLI');
  });

  it('calls onSend when send button clicked with content', () => {
    const onSend = vi.fn();
    renderWithProviders(<ChatInputBar onSend={onSend} />);
    const textarea = screen.getByTestId('chat-composer-input');
    fireEvent.change(textarea, { target: { value: 'hello world' } });
    fireEvent.click(screen.getByTestId('composer-send-btn'));
    expect(onSend).toHaveBeenCalledWith('hello world', undefined);
  });
});
