import { expect, type APIRequestContext, type Page } from '@playwright/test';

type WireEnvelope<T> = {
  ok: boolean;
  data?: T;
  error?: string | null;
};

type WireProject = {
  id: string;
};

export async function ensureBoardReady(
  page: Page,
  request: APIRequestContext,
): Promise<void> {
  const created = await request.post('/api/projects', {
    data: { name: `E2E Project ${Date.now()}` },
  });
  expect(created.ok()).toBeTruthy();
  const projectEnvelope = (await created.json()) as WireEnvelope<WireProject>;
  expect(projectEnvelope.ok).toBeTruthy();
  const projectId = projectEnvelope.data?.id;
  expect(projectId).toBeTruthy();

  const activated = await request.post(`/api/projects/${projectId}/activate`);
  expect(activated.ok()).toBeTruthy();

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
