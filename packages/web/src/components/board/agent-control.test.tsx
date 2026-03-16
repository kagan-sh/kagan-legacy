import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { createStore } from 'jotai';
import { renderWithProviders } from '@/test/render';
import { AgentControl } from '@/components/board/agent-control';
import { wsConnectedAtom } from '@/lib/atoms/connection';

vi.mock('@/lib/api/websocket', () => ({
  kaganWs: { startRun: vi.fn(), cancelRun: vi.fn(), on: vi.fn(() => vi.fn()), off: vi.fn() },
}));

describe('AgentControl', () => {
  it('shows Start when idle', () => {
    const store = createStore();
    store.set(wsConnectedAtom, true);
    renderWithProviders(<AgentControl taskId="t1" status="BACKLOG" />, { store });
    expect(screen.getByText('Start')).toBeVisible();
  });

  it('shows Stop when running', () => {
    const store = createStore();
    store.set(wsConnectedAtom, true);
    renderWithProviders(<AgentControl taskId="t1" status="IN_PROGRESS" />, { store });
    expect(screen.getByText('Stop')).toBeVisible();
  });

  it('disables Start when disconnected', () => {
    const store = createStore();
    store.set(wsConnectedAtom, false);
    renderWithProviders(<AgentControl taskId="t1" status="BACKLOG" />, { store });
    expect(screen.getByText('Start').closest('button')).toBeDisabled();
  });

  it('uses startedAt to persist elapsed timer', () => {
    vi.useFakeTimers();
    vi.setSystemTime(new Date('2026-01-01T12:00:20.000Z'));

    const store = createStore();
    store.set(wsConnectedAtom, true);

    renderWithProviders(
      <AgentControl taskId="t1" status="IN_PROGRESS" startedAt="2026-01-01T12:00:00.000Z" />,
      { store },
    );

    expect(screen.getByText('0:20')).toBeVisible();

    vi.useRealTimers();
  });
});
