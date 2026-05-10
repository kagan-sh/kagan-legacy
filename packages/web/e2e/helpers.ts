import { expect, type APIRequestContext, type APIResponse, type Page } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { mkdtempSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';
import { execSync } from 'node:child_process';

type WireEnvelope<T> = {
  ok: boolean;
  data?: T;
  error?: string | null;
};

type WireProject = {
  id: string;
  active?: boolean;
};

type WireTask = {
  id: string;
};

type WireRepository = {
  id: string;
  selected?: boolean;
};

type E2EProject = {
  projectId: string;
  repoId: string;
};

const fixturePromises = new Map<string, Promise<E2EProject>>();

async function expectOk(response: APIResponse, label: string): Promise<void> {
  if (response.ok()) return;
  throw new Error(`${label} failed with ${response.status()}: ${await response.text()}`);
}

async function createFixture(request: APIRequestContext): Promise<E2EProject> {
  const created = await request.post('/api/projects', {
    data: { name: `E2E Project ${randomUUID()}` },
  });
  await expectOk(created, 'create project');
  const projectEnvelope = (await created.json()) as WireEnvelope<WireProject>;
  expect(projectEnvelope.ok).toBeTruthy();
  const projectId = projectEnvelope.data?.id;
  expect(projectId).toBeTruthy();

  const repoPath = mkdtempSync(join(tmpdir(), 'kagan-e2e-repo-'));
  execSync('git init', { cwd: repoPath });
  execSync('git config user.email "e2e@test.com"', { cwd: repoPath });
  execSync('git config user.name "E2E Tester"', { cwd: repoPath });
  execSync('git checkout -b main', { cwd: repoPath });
  execSync('git commit --allow-empty -m "init"', { cwd: repoPath });
  const repoCreated = await request.post(`/api/projects/${projectId}/repos`, {
    data: { path: repoPath },
  });
  await expectOk(repoCreated, 'create repository');
  const repoEnvelope = (await repoCreated.json()) as WireEnvelope<WireRepository>;
  expect(repoEnvelope.ok).toBeTruthy();
  const repoId = repoEnvelope.data?.id;
  expect(repoId).toBeTruthy();

  const activated = await request.post(`/api/projects/${projectId}/activate`, { data: {} });
  await expectOk(activated, 'activate project');

  const selected = await request.post(`/api/projects/${projectId}/repos/${repoId}/select`, {
    data: {},
  });
  await expectOk(selected, 'select repository');

  const taskCreated = await request.post('/api/tasks', {
    data: { title: 'E2E seed task', repo_id: repoId },
  });
  await expectOk(taskCreated, 'create seed task');

  return { projectId: projectId!, repoId: repoId! };
}

async function fixtureIsUsable(
  request: APIRequestContext,
  fixture: E2EProject,
): Promise<boolean> {
  const projects = await request.get('/api/projects');
  if (!projects.ok()) return false;
  const projectEnvelope = (await projects.json()) as WireEnvelope<WireProject[]>;
  const project = projectEnvelope.data?.find((candidate) => candidate.id === fixture.projectId);
  if (!project) return false;

  const repos = await request.get(`/api/projects/${fixture.projectId}/repos`);
  if (!repos.ok()) return false;
  const repoEnvelope = (await repos.json()) as WireEnvelope<WireRepository[]>;
  const repo = repoEnvelope.data?.find((candidate) => candidate.id === fixture.repoId);
  if (!repo) return false;

  if (!project.active) {
    const activated = await request.post(`/api/projects/${fixture.projectId}/activate`, { data: {} });
    if (!activated.ok()) return false;
  }
  if (!repo.selected) {
    const selected = await request.post(`/api/projects/${fixture.projectId}/repos/${fixture.repoId}/select`, {
      data: {},
    });
    if (!selected.ok()) return false;
  }
  return true;
}

async function getFixture(request: APIRequestContext): Promise<E2EProject> {
  const workerKey = process.env.TEST_WORKER_INDEX ?? 'default';
  const existing = fixturePromises.get(workerKey);
  if (existing) {
    const fixture = await existing;
    if (await fixtureIsUsable(request, fixture)) return fixture;
    fixturePromises.delete(workerKey);
  }

  const created = createFixture(request).catch((error: unknown) => {
    fixturePromises.delete(workerKey);
    throw error;
  });
  fixturePromises.set(workerKey, created);
  return created;
}

export async function waitForTaskSessions(
  request: APIRequestContext,
  taskId: string,
  opts?: { timeoutMs?: number; intervalMs?: number },
): Promise<void> {
  const timeoutMs = opts?.timeoutMs ?? 20_000;
  const intervalMs = opts?.intervalMs ?? 400;
  const deadline = Date.now() + timeoutMs;
  let lastStatus = 0;
  while (Date.now() < deadline) {
    const resp = await request.get(`/api/tasks/${taskId}/sessions`);
    lastStatus = resp.status();
    if (resp.ok()) {
      const envelope = (await resp.json()) as WireEnvelope<unknown[]>;
      const rows = envelope.data;
      if (envelope.ok && Array.isArray(rows) && rows.length > 0) {
        return;
      }
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error(
    `No sessions for task ${taskId} within ${timeoutMs}ms (last HTTP ${lastStatus})`,
  );
}

export async function waitForTaskStatus(
  request: APIRequestContext,
  taskId: string,
  status: string,
  opts?: { timeoutMs?: number; intervalMs?: number },
): Promise<void> {
  const timeoutMs = opts?.timeoutMs ?? 20_000;
  const intervalMs = opts?.intervalMs ?? 400;
  const deadline = Date.now() + timeoutMs;
  let lastStatus = '';
  while (Date.now() < deadline) {
    const resp = await request.get(`/api/tasks/${taskId}`);
    if (resp.ok()) {
      const envelope = (await resp.json()) as WireEnvelope<{ status: string }>;
      if (envelope.ok && envelope.data?.status === status) {
        return;
      }
      lastStatus = envelope.data?.status ?? 'unknown';
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error(
    `Task ${taskId} never reached status ${status} within ${timeoutMs}ms (last: ${lastStatus})`,
  );
}

/** Wait until the sandboxed web server responds on `/health` (boot-complete). */
export async function waitForServerHealthy(
  request: APIRequestContext,
  attempts = 40,
  intervalMs = 250,
): Promise<void> {
  let lastStatus = 0;
  for (let i = 0; i < attempts; i += 1) {
    const resp = await request.get('/health');
    if (resp.ok()) return;
    lastStatus = resp.status();
    await new Promise((r) => setTimeout(r, intervalMs));
  }
  throw new Error(`/health did not return OK after ${attempts} attempts (last status ${lastStatus})`);
}

export async function ensureBoardReady(
  page: Page,
  request: APIRequestContext,
): Promise<void> {
  await waitForServerHealthy(request);
  await ensureProjectReady(request);

  await page.goto('/board');
  await page.waitForLoadState('load');
  const tutorial = page.getByRole('dialog', { name: /Guided Tutorial/i });
  if (await tutorial.isVisible().catch(() => false)) {
    await page.keyboard.press('Escape');
    await expect(tutorial).toBeHidden();
  }
  await expect(page.getByRole('heading', { name: 'Backlog', exact: true })).toBeVisible({
    timeout: 20_000,
  });
  // Board toolbar uses aria-label="Create new task" (text "New task") in the new shell.
  await expect(page.getByRole('button', { name: 'Create new task' })).toBeVisible({
    timeout: 20_000,
  });
}

export async function ensureProjectReady(
  request: APIRequestContext,
): Promise<E2EProject> {
  return getFixture(request);
}

export async function createTaskViaApi(
  request: APIRequestContext,
  title: string,
): Promise<string> {
  const { repoId } = await ensureProjectReady(request);
  const created = await request.post('/api/tasks', {
    data: { title, repo_id: repoId },
  });
  await expectOk(created, 'create task');

  const taskEnvelope = (await created.json()) as WireEnvelope<WireTask>;
  expect(taskEnvelope.ok).toBeTruthy();
  expect(taskEnvelope.data?.id).toBeTruthy();
  return taskEnvelope.data!.id;
}

/**
 * Create a task and POST /api/tasks/:id/run to start an agent session.
 *
 * Requires the server to be booted with KAGAN_FAKE_AGENT=1 (or --fake-agent)
 * so that a deterministic fake-agent backend is available and the run can
 * reach RUNNING status without a real coding agent installed.
 *
 * Returns the task id. The task status transitions asynchronously; callers
 * should poll /api/v1/agents/running or wait for UI markers rather than
 * relying on the response body status field.
 */
export async function createTaskAndRun(
  request: APIRequestContext,
  title: string,
): Promise<string> {
  const taskId = await createTaskViaApi(request, title);

  const runResp = await request.post(`/api/tasks/${taskId}/run`, {
    data: { agent_backend: 'fake-agent' },
  });
  await expectOk(runResp, 'run task with fake-agent');

  return taskId;
}

/**
 * Create a task, schedule a fake-agent scenario, then start the run.
 *
 * This avoids the race condition where `createTaskAndRun` starts the agent
 * before the scenario is scheduled, causing the agent to use its default
 * behaviour instead of the custom script.
 */
export async function createTaskAndRunWithScenario(
  request: APIRequestContext,
  title: string,
  scenarioOrFn: FakeScenario | ((taskId: string) => FakeScenario),
): Promise<string> {
  const taskId = await createTaskViaApi(request, title);
  const scenario = typeof scenarioOrFn === 'function' ? scenarioOrFn(taskId) : scenarioOrFn;
  await scheduleScenario(request, scenario);

  const runResp = await request.post(`/api/tasks/${taskId}/run`, {
    data: { agent_backend: 'fake-agent' },
  });
  await expectOk(runResp, 'run task with fake-agent');

  return taskId;
}

// ---------------------------------------------------------------------------
// Scenario DSL — declarative fake-agent scripts
// ---------------------------------------------------------------------------

export type FakeCue = {
  wait?: number;
  emit?: { type: 'chunk'; text: string } | { type: 'tool_use'; name: string; input?: unknown } | { type: 'tool_result'; tool_use_id: string; output?: string } | { type: 'status'; usage: Record<string, unknown> };
  workspace?: { write_file?: { path: string; content: string }; commit?: { message?: string } };
  done?: boolean;
  error?: string;
};

export type FakeScenario = {
  targetId: string;
  cues: FakeCue[];
};

/**
 * Schedule a fake-agent script for a task or session.
 *
 * The script is sent to the internal ``/api/e2e/fake-agent/schedule`` endpoint
 * which is only available when the server is started with ``--fake-agent``.
 */
export async function scheduleScenario(
  request: APIRequestContext,
  scenario: FakeScenario,
): Promise<void> {
  const resp = await request.post('/api/e2e/fake-agent/schedule', {
    data: {
      target_id: scenario.targetId,
      cues: scenario.cues,
    },
  });
  await expectOk(resp, 'schedule fake-agent scenario');
}

/** Shorthand for a single-chunk immediate completion. */
export function quickComplete(targetId: string, text = 'Done.'): FakeScenario {
  return {
    targetId,
    cues: [{ emit: { type: 'chunk', text }, done: true }],
  };
}

/** Shorthand for a review-gate scenario: writes a file and commits. */
export function reviewGate(targetId: string, filePath = 'feat.md', content = '# Feature\n'): FakeScenario {
  return {
    targetId,
    cues: [
      { wait: 0.1, emit: { type: 'chunk', text: 'Analysing...' } },
      { wait: 0.2, emit: { type: 'chunk', text: `Writing ${filePath}...` } },
      { wait: 0.3, workspace: { write_file: { path: filePath, content }, commit: { message: `feat: add ${filePath}` } } },
      { wait: 0.1, emit: { type: 'chunk', text: 'Complete.' }, done: true },
    ],
  };
}

/** Shorthand for a chat echo responder. */
export function chatEcho(targetId: string, reply = 'Hello from fake agent.'): FakeScenario {
  return {
    targetId,
    cues: [
      { wait: 0.1, emit: { type: 'chunk', text: reply }, done: true },
    ],
  };
}

/** Shorthand for a permission-gate scenario. */
export function permissionGate(targetId: string, toolName = 'write_file'): FakeScenario {
  return {
    targetId,
    cues: [
      { wait: 0.1, emit: { type: 'chunk', text: 'I need to write a file.' } },
      { wait: 0.2, emit: { type: 'tool_use', name: toolName, input: { path: 'test.txt', content: 'hello' } } },
      // The fake agent pauses here — the test must grant permission via the real UI.
    ],
  };
}

/** Clear a scheduled scenario so the default behaviour is used. */
export async function clearScenario(request: APIRequestContext, targetId: string): Promise<void> {
  const resp = await request.post('/api/e2e/fake-agent/clear', {
    data: { target_id: targetId },
  });
  await expectOk(resp, 'clear fake-agent scenario');
}
