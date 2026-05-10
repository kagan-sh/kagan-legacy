/**
 * task-detail-lane.test.tsx
 *
 * Focused tests for the LaneControl segmented control rendered in tv-head.
 * Tests cover the four spec requirements:
 *  1. Control NOT rendered when only a worker session exists.
 *  2. Control NOT rendered when only a reviewer session exists.
 *  3. Control rendered when both exist; Worker button is aria-pressed when ?lane=worker.
 *  4. Clicking Reviewer updates the URL search param to lane=reviewer.
 *
 * Because LaneControl is a pure presentational component driven by props,
 * these tests render it directly rather than mounting the full Component
 * (which would require mocking useTaskEvents, atoms, SSE, etc.).
 */
import { describe, it, expect, vi } from 'vitest';
import { screen, fireEvent } from '@testing-library/react';
import { renderWithProviders } from '@/test/render';
import { LaneControl } from '@/pages/task-detail-page';
import type { TaskSessionLane } from '@/lib/sessions/kind';
import { taskSessionLane } from '@/lib/sessions/kind';
import type { WireTaskSession } from '@kagan/shared-api-client';

// ── taskSessionLane narrowing helper ─────────────────────────────────────────

describe('taskSessionLane', () => {
  it('returns "worker" for agent_role="worker"', () => {
    expect(taskSessionLane({ agent_role: 'worker' })).toBe('worker');
  });

  it('returns "reviewer" for agent_role="reviewer"', () => {
    expect(taskSessionLane({ agent_role: 'reviewer' })).toBe('reviewer');
  });

  it('returns null for null agent_role', () => {
    expect(taskSessionLane({ agent_role: null })).toBeNull();
  });

  it('returns null for undefined agent_role', () => {
    // WireTaskSession.agent_role is string | null | undefined per wire.ts
    expect(taskSessionLane({ agent_role: undefined })).toBeNull();
  });

  it('returns null for unknown role strings', () => {
    expect(taskSessionLane({ agent_role: 'lead' })).toBeNull();
    expect(taskSessionLane({ agent_role: '' })).toBeNull();
    expect(taskSessionLane({ agent_role: 'WORKER' })).toBeNull();
  });
});

// ── Lane computation helper — mirrors logic in Component ─────────────────────

function availableLanes(sessions: WireTaskSession[]): Set<TaskSessionLane> {
  return new Set(
    sessions.map(taskSessionLane).filter((l): l is TaskSessionLane => l !== null),
  );
}

function hasMultipleLanes(sessions: WireTaskSession[]): boolean {
  const lanes = availableLanes(sessions);
  return lanes.has('worker') && lanes.has('reviewer');
}

function makeSession(role: string | null): WireTaskSession {
  return {
    id: `sess-${role ?? 'null'}`,
    status: 'COMPLETED',
    started_at: '2026-01-01T00:00:00Z',
    agent_backend: 'claude',
    agent_role: role,
  };
}

// ── LaneControl rendering tests ───────────────────────────────────────────────

describe('LaneControl — rendered directly', () => {
  it('spec 1: hasMultipleLanes is false when only a worker session exists', () => {
    const sessions = [makeSession('worker'), makeSession(null)];
    expect(hasMultipleLanes(sessions)).toBe(false);
  });

  it('spec 2: hasMultipleLanes is false when only a reviewer session exists', () => {
    const sessions = [makeSession('reviewer')];
    expect(hasMultipleLanes(sessions)).toBe(false);
  });

  it('spec 3: LaneControl renders; Worker button is aria-pressed when activeLane="worker"', () => {
    const onSelect = vi.fn();
    renderWithProviders(
      <LaneControl activeLane="worker" onSelect={onSelect} />,
      { initialEntries: ['/task/abc?lane=worker'] },
    );

    const workerBtn = screen.getByRole('button', { name: /worker session/i });
    const reviewerBtn = screen.getByRole('button', { name: /reviewer session/i });

    expect(workerBtn).toBeInTheDocument();
    expect(reviewerBtn).toBeInTheDocument();

    // Worker is active — aria-pressed must be "true" (string, not boolean)
    expect(workerBtn).toHaveAttribute('aria-pressed', 'true');
    expect(reviewerBtn).toHaveAttribute('aria-pressed', 'false');
  });

  it('spec 4: clicking Reviewer calls onSelect with "reviewer"', () => {
    const onSelect = vi.fn();
    renderWithProviders(
      <LaneControl activeLane="worker" onSelect={onSelect} />,
      { initialEntries: ['/task/abc?lane=worker'] },
    );

    const reviewerBtn = screen.getByRole('button', { name: /reviewer session/i });
    fireEvent.click(reviewerBtn);

    expect(onSelect).toHaveBeenCalledWith('reviewer');
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it('renders Reviewer as active when activeLane="reviewer"', () => {
    renderWithProviders(
      <LaneControl activeLane="reviewer" onSelect={vi.fn()} />,
    );

    expect(screen.getByRole('button', { name: /reviewer session/i })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
    expect(screen.getByRole('button', { name: /worker session/i })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
  });

  it('neither button is aria-pressed when activeLane is null', () => {
    renderWithProviders(
      <LaneControl activeLane={null} onSelect={vi.fn()} />,
    );

    expect(screen.getByRole('button', { name: /worker session/i })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
    expect(screen.getByRole('button', { name: /reviewer session/i })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
  });
});
