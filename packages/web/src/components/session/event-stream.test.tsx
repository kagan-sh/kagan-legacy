import { describe, it, expect } from 'vitest';
import { screen } from '@testing-library/react';
import { EVENT_TYPE } from '@kagan/shared-api-client';
import { renderWithProviders } from '@/test/render';
import { EventStream } from '@/components/session/event-stream';
import { mockEvent } from '@/test/mocks';

describe('EventStream', () => {
  it('shows empty state when no events', () => {
    renderWithProviders(<EventStream events={[]} />);
    expect(screen.getByText('What are you working on?')).toBeVisible();
    expect(screen.getByText(/\/flow <goal>/)).toBeVisible();
  });

  it('renders agent messages and tool calls', () => {
    const events = [
      mockEvent({ type: EVENT_TYPE.OUTPUT_CHUNK, payload: { text: 'Hello from the agent' } }),
      mockEvent({ type: EVENT_TYPE.TOOL_CALL_START, payload: { acp: { toolCallId: 'tc-1', toolName: 'read_file' } } }),
      mockEvent({ type: EVENT_TYPE.TASK_STATUS_CHANGED, payload: { from: 'BACKLOG', to: 'IN_PROGRESS' } }),
    ];
    renderWithProviders(<EventStream events={events} />);
    expect(screen.getByText('Agent')).toBeVisible();
    expect(screen.getByText('read file')).toBeVisible();
    expect(screen.getByText('Status: BACKLOG → IN_PROGRESS')).toBeVisible();
  });

  it('renders user follow-up messages interleaved with events', () => {
    const events = [
      mockEvent({ type: EVENT_TYPE.OUTPUT_CHUNK, payload: { text: 'Working on it...' }, created_at: '2026-03-14T10:00:00Z' }),
    ];
    const followUps = [
      { text: 'Please also fix the tests', timestamp: '2026-03-14T10:01:00Z' },
    ];
    renderWithProviders(<EventStream events={events} userFollowUps={followUps} />);
    expect(screen.getByText('Agent')).toBeVisible();
    expect(screen.getByText('You')).toBeVisible();
    expect(screen.getByText('Please also fix the tests')).toBeVisible();
  });

  it('formats MCP tool names nicely', () => {
    const events = [
      mockEvent({ type: EVENT_TYPE.TOOL_CALL_START, payload: { acp: { toolCallId: 'tc-2', toolName: 'mcp__kagan__run_wait' } } }),
    ];
    renderWithProviders(<EventStream events={events} />);
    expect(screen.getByText('kagan / run_wait')).toBeVisible();
  });

  it('extracts tool name from alternate payload fields', () => {
    const events = [
      mockEvent({ type: EVENT_TYPE.TOOL_CALL_START, payload: { name: 'bash_tool', id: 'tc-3' } }),
    ];
    renderWithProviders(<EventStream events={events} />);
    expect(screen.getByText('bash tool')).toBeVisible();
  });

  it('shows LIVE indicator when isRunning is true', () => {
    const events = [
      mockEvent({ type: EVENT_TYPE.OUTPUT_CHUNK, payload: { text: 'Working...' } }),
    ];
    renderWithProviders(<EventStream events={events} isRunning />);
    expect(screen.getByText('Live')).toBeVisible();
  });

  it('shows startup state when isRunning with no events', () => {
    renderWithProviders(<EventStream events={[]} isRunning />);
    expect(screen.getByText('Agent is starting up...')).toBeVisible();
    expect(screen.getByText('Events will appear here as the agent works.')).toBeVisible();
    expect(screen.getByText('Live')).toBeVisible();
  });

  it('does not show LIVE indicator when isRunning is false', () => {
    const events = [
      mockEvent({ type: EVENT_TYPE.OUTPUT_CHUNK, payload: { text: 'Done.' } }),
    ];
    renderWithProviders(<EventStream events={events} isRunning={false} />);
    expect(screen.queryByText('Live')).toBeNull();
  });
});
