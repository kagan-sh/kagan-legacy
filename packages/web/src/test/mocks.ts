import type { AcceptanceCriterionResponse, WireChatSession, WireEvent, WireProject, WireRepository, WireTask } from '@/lib/api/types';

let idCounter = 0;

function nextId(): string {
  return `test-${++idCounter}`;
}

export function mockTask(overrides: Partial<WireTask> = {}): WireTask {
  return {
    id: nextId(),
    title: 'Test task',
    description: 'A test task description',
    status: 'BACKLOG',
    priority: 'MEDIUM',
    review_running: false,
    ...overrides,
  };
}

export function mockTaskInProgress(overrides: Partial<WireTask> = {}): WireTask {
  return mockTask({
    status: 'IN_PROGRESS',
    active_session: {
      id: nextId(),
      status: 'running',
      launcher: null,
      agent_backend: 'claude-code',
      started_at: new Date().toISOString(),
    },
    ...overrides,
  });
}

export function mockTaskInReview(overrides: Partial<WireTask> = {}): WireTask {
  return mockTask({
    status: 'REVIEW',
    ...overrides,
  });
}

export function mockProject(overrides: Partial<WireProject> = {}): WireProject {
  return {
    id: nextId(),
    name: 'Test project',
    active: false,
    ...overrides,
  };
}

export function mockRepository(overrides: Partial<WireRepository> = {}): WireRepository {
  return {
    id: nextId(),
    project_id: nextId(),
    name: 'test-repo',
    path: '/tmp/test-repo',
    default_branch: 'main',
    ...overrides,
  };
}

export function mockChatSession(overrides: Partial<WireChatSession> = {}): WireChatSession {
  return {
    id: nextId(),
    label: 'Test chat',
    source: 'web',
    updated_at: new Date().toISOString(),
    message_count: 0,
    messages: [],
    ...overrides,
  };
}

export function mockCriterion(
  overrides: Partial<AcceptanceCriterionResponse> & { task_id?: string } = {},
): AcceptanceCriterionResponse {
  return {
    id: nextId(),
    task_id: overrides.task_id ?? nextId(),
    ordinal: 0,
    text: 'Test criterion',
    ...overrides,
  };
}

export function mockEvent(overrides: Partial<WireEvent> = {}): WireEvent {
  return {
    id: nextId(),
    session_id: nextId(),
    type: 'agent_start',
    created_at: new Date().toISOString(),
    ...overrides,
  };
}
