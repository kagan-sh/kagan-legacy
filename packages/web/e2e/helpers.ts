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

let fixturePromise: Promise<E2EProject> | null = null;

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

async function getFixture(request: APIRequestContext): Promise<E2EProject> {
  fixturePromise ??= createFixture(request).catch((error: unknown) => {
    fixturePromise = null;
    throw error;
  });
  return fixturePromise;
}

export async function ensureBoardReady(
  page: Page,
  request: APIRequestContext,
): Promise<void> {
  await ensureProjectReady(request);

  await page.goto('/board');
  await page.waitForLoadState('load');
  const tutorial = page.getByRole('dialog', { name: /Guided Tutorial/i });
  if (await tutorial.isVisible().catch(() => false)) {
    await page.keyboard.press('Escape');
    await expect(tutorial).toBeHidden();
  }
  await expect(page.getByRole('heading', { name: 'Backlog', exact: true })).toBeVisible();
  await expect(page.getByRole('button', { name: 'New', exact: true })).toBeVisible();
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
