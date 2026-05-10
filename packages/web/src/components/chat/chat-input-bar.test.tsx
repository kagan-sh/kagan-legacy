import { describe, it, expect, vi, beforeEach } from 'vitest';
import { fireEvent, screen } from '@testing-library/react';
import { createStore } from 'jotai';
import { renderWithProviders } from '@/test/render';
import { ChatInputBar } from './chat-input-bar';
import {
  shellPopoverAtom,
  composerAccessAtom,
  composerLocalityAtom,
  currentModelAtom,
} from '@/lib/atoms/shell';

// navigator.clipboard is not available in jsdom — stub it
const writeTextMock = vi.fn().mockResolvedValue(undefined);
Object.defineProperty(navigator, 'clipboard', {
  value: { writeText: writeTextMock },
  writable: true,
  configurable: true,
});

const noop = () => {};

describe('ChatInputBar chip row', () => {
  beforeEach(() => {
    writeTextMock.mockClear();
  });

  it('renders all chip-row buttons', () => {
    renderWithProviders(<ChatInputBar onSend={noop} />);
    expect(screen.getByTestId('composer-attach-btn')).toBeInTheDocument();
    expect(screen.getByTestId('composer-permissions-chip')).toBeInTheDocument();
    expect(screen.getByTestId('composer-locality-chip')).toBeInTheDocument();
    expect(screen.getByTestId('composer-branch-chip')).toBeInTheDocument();
    expect(screen.getByTestId('composer-model-chip')).toBeInTheDocument();
    expect(screen.getByTestId('composer-voice-btn')).toBeInTheDocument();
    expect(screen.getByTestId('composer-send-btn')).toBeInTheDocument();
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

  it('permissions chip opens permissions popover via shellPopoverAtom', () => {
    const store = createStore();
    renderWithProviders(<ChatInputBar onSend={noop} />, { store });

    fireEvent.click(screen.getByTestId('composer-permissions-chip'));

    const popover = store.get(shellPopoverAtom);
    expect(popover.kind).toBe('permissions');
  });

  it('locality chip opens locality popover via shellPopoverAtom', () => {
    const store = createStore();
    renderWithProviders(<ChatInputBar onSend={noop} />, { store });

    fireEvent.click(screen.getByTestId('composer-locality-chip'));

    const popover = store.get(shellPopoverAtom);
    expect(popover.kind).toBe('locality');
  });

  it('model chip opens model popover via shellPopoverAtom', () => {
    const store = createStore();
    renderWithProviders(<ChatInputBar onSend={noop} />, { store });

    fireEvent.click(screen.getByTestId('composer-model-chip'));

    const popover = store.get(shellPopoverAtom);
    expect(popover.kind).toBe('model');
  });

  it('branch chip copies branch to clipboard (default main)', async () => {
    renderWithProviders(<ChatInputBar onSend={noop} />);

    fireEvent.click(screen.getByTestId('composer-branch-chip'));

    await vi.waitFor(() => {
      expect(writeTextMock).toHaveBeenCalledWith('main');
    });
  });

  it('branch chip copies activeBranch prop when provided', async () => {
    renderWithProviders(<ChatInputBar onSend={noop} activeBranch="feat/my-task" />);

    fireEvent.click(screen.getByTestId('composer-branch-chip'));

    await vi.waitFor(() => {
      expect(writeTextMock).toHaveBeenCalledWith('feat/my-task');
    });
  });

  it('permissions chip label reflects composerAccessAtom', () => {
    const store = createStore();
    store.set(composerAccessAtom, 'readonly');
    renderWithProviders(<ChatInputBar onSend={noop} />, { store });
    expect(screen.getByTestId('composer-permissions-chip')).toHaveTextContent('Read-only');
  });

  it('locality chip label reflects composerLocalityAtom', () => {
    const store = createStore();
    store.set(composerLocalityAtom, 'remote');
    renderWithProviders(<ChatInputBar onSend={noop} />, { store });
    expect(screen.getByTestId('composer-locality-chip')).toHaveTextContent('Remote');
  });

  it('model chip label reflects currentModelAtom', () => {
    const store = createStore();
    store.set(currentModelAtom, 'claude-code');
    renderWithProviders(<ChatInputBar onSend={noop} />, { store });
    expect(screen.getByTestId('composer-model-chip')).toHaveTextContent('claude-code');
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
