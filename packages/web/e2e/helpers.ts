import { expect, type APIRequestContext, type APIResponse, type Page } from '@playwright/test';
import { randomUUID } from 'node:crypto';
import { mkdtempSync } from 'node:fs';
import { join } from 'node:path';
import { tmpdir } from 'node:os';

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
  await expect(page.getByRole('button', { name: 'New', exact: true })).toBeVisible({
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
