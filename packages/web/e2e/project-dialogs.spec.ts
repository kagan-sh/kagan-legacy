import { randomUUID } from "node:crypto";
import type { APIRequestContext, Page } from "@playwright/test";
import { expect, test } from "./coverage-fixture";
import { ensureBoardReady, ensureProjectReady } from "./helpers";

type WireEnvelope<T> = { ok: boolean; data?: T };

async function activateRepolessProject(request: APIRequestContext): Promise<string> {
  const created = await request.post("/api/projects", {
    data: { name: `E2E AddRepo ${randomUUID()}` },
  });
  expect(created.ok()).toBeTruthy();
  const envelope = (await created.json()) as WireEnvelope<{ id: string }>;
  const projectId = envelope.data?.id;
  expect(projectId).toBeTruthy();

  const activated = await request.post(`/api/projects/${projectId}/activate`, {
    data: {},
  });
  expect(activated.ok()).toBeTruthy();
  return projectId!;
}

async function openAddRepoDialog(page: Page): Promise<void> {
  await page.getByRole("button", { name: /switch project/i }).click();
  await page.getByRole("menuitem", { name: /add repository/i }).click();
  await expect(page.getByRole("dialog")).toBeVisible();
}

test.describe("Project dialogs", () => {
  test.describe.configure({ timeout: 90_000 });

  test.afterEach(async ({ request }) => {
    await ensureProjectReady(request);
  });

  test("add-repo dialog open and cancel", async ({ page, request }) => {
    await ensureBoardReady(page, request);
    await activateRepolessProject(request);
    await page.reload();
    await page.waitForLoadState("load");

    await page.getByRole("button", { name: /switch project/i }).click();
    await page.getByRole("menuitem", { name: /add repository/i }).click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(dialog.getByText(/add repository/i).first()).toBeVisible();
    await expect(dialog.getByPlaceholder("/path/to/repository")).toBeVisible();

    await dialog.getByRole("button", { name: /^cancel$/i }).click();
    await expect(dialog).toBeHidden();
  });

  // FIXME: AddRepoDialog disables Add when empty instead of inline validation.
  test.skip("validates empty path before submitting", async ({ page, request }) => {
    await ensureBoardReady(page, request);
    await activateRepolessProject(request);
    await page.reload();
    await page.waitForLoadState("load");

    await openAddRepoDialog(page);
    await page.getByRole("button", { name: /^add$/i }).click();
    await expect(page.getByText(/path/i)).toBeVisible();
  });
});
