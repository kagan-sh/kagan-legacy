/**
 * chat-attach atom transitions
 *
 * Tests for chatAttachAtom, attachChatSessionAtom, detachChatSessionAtom.
 */

import { describe, it, expect, beforeEach } from 'vitest';
import { createStore } from 'jotai';
import {
  chatAttachAtom,
  attachChatSessionAtom,
  cycleChatAttachAtom,
  detachChatSessionAtom,
  type ChatAttachTarget,
} from '@/lib/atoms/chat-attach';
import { setRunningAgentsAtom } from '@/lib/atoms/running-agents';
import type { ActiveAgentRowResponse } from '@kagan/shared-api-client';

function makeTarget(overrides: Partial<ChatAttachTarget> = {}): ChatAttachTarget {
  return {
    attachedSessionId: 'session-1',
    taskTitle: 'Fix the bug',
    role: 'worker',
    startedAt: new Date().toISOString(),
    inputTokens: 1000,
    outputTokens: 500,
    ...overrides,
  };
}

function makeAgent(sessionId: string, taskTitle: string): ActiveAgentRowResponse {
  return {
    task_id: `task-${sessionId}`,
    task_title: taskTitle,
    task_status: 'IN_PROGRESS',
    session_id: sessionId,
    agent_role: 'worker',
    agent_backend: 'claude-code',
    session_status: 'running',
    started_at: new Date().toISOString(),
    last_event_at: null,
    input_tokens: 100,
    output_tokens: 50,
  };
}

describe('chatAttachAtom', () => {
  let store: ReturnType<typeof createStore>;

  beforeEach(() => {
    store = createStore();
  });

  it('starts as null (orchestrator mode)', () => {
    expect(store.get(chatAttachAtom)).toBeNull();
  });

  it('attachChatSessionAtom sets the target', () => {
    const target = makeTarget();
    store.set(attachChatSessionAtom, target);
    expect(store.get(chatAttachAtom)).toEqual(target);
  });

  it('attachChatSessionAtom works for reviewer role', () => {
    const target = makeTarget({ role: 'reviewer', attachedSessionId: 'rev-1' });
    store.set(attachChatSessionAtom, target);
    const result = store.get(chatAttachAtom);
    expect(result?.role).toBe('reviewer');
    expect(result?.attachedSessionId).toBe('rev-1');
  });

  it('detachChatSessionAtom resets to null', () => {
    store.set(attachChatSessionAtom, makeTarget());
    expect(store.get(chatAttachAtom)).not.toBeNull();

    store.set(detachChatSessionAtom);
    expect(store.get(chatAttachAtom)).toBeNull();
  });

  it('multiple attach calls replace previous target', () => {
    store.set(attachChatSessionAtom, makeTarget({ attachedSessionId: 'session-1' }));
    store.set(attachChatSessionAtom, makeTarget({ attachedSessionId: 'session-2' }));
    expect(store.get(chatAttachAtom)?.attachedSessionId).toBe('session-2');
  });

  it('preserves null token fields', () => {
    const target = makeTarget({ inputTokens: null, outputTokens: null });
    store.set(attachChatSessionAtom, target);
    const result = store.get(chatAttachAtom);
    expect(result?.inputTokens).toBeNull();
    expect(result?.outputTokens).toBeNull();
  });

  it('cycleChatAttachAtom walks orchestrator and running agents by session id', () => {
    store.set(setRunningAgentsAtom, [
      makeAgent('session-1', 'Task A'),
      makeAgent('session-2', 'Task B'),
    ]);

    store.set(cycleChatAttachAtom, 1);
    expect(store.get(chatAttachAtom)?.attachedSessionId).toBe('session-1');

    store.set(cycleChatAttachAtom, 1);
    expect(store.get(chatAttachAtom)?.attachedSessionId).toBe('session-2');

    store.set(cycleChatAttachAtom, 1);
    expect(store.get(chatAttachAtom)).toBeNull();

    store.set(cycleChatAttachAtom, -1);
    expect(store.get(chatAttachAtom)?.attachedSessionId).toBe('session-2');
  });
});
