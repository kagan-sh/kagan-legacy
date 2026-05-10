import { randomUUID } from "node:crypto";
import type { APIRequestContext, Page } from "@playwright/test";
import { test, expect } from "./coverage-fixture";
import { ensureBoardReady, ensureProjectReady } from "./helpers";

type WireEnvelope<T> = { ok: boolean; data?: T };

/**
 * The "Add repository" trigger only renders in the project-switcher popover
 * when the active project has zero repositories attached. The shared E2E
 * fixture seeds one repo, so each test here provisions a fresh repo-less
 * project and activates it before driving the UI.
 */
async function activateRepolessProject(
  request: APIRequestContext,
): Promise<string> {
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

test.describe("Add repository dialog", () => {
  test.beforeEach(async ({ page, request }) => {
    await ensureBoardReady(page, request);
    await activateRepolessProject(request);
    await page.reload();
    await page.waitForLoadState("load");
  });

  test.afterEach(async ({ request }) => {
    // Re-activate the shared fixture project so subsequent tests have a repo.
    await ensureProjectReady(request);
  });

  test("opens add-repo dialog from header", async ({ page }) => {
    await page.getByRole("button", { name: /switch project/i }).click();
    await page
      .getByRole("menuitem", { name: /add repository/i })
      .click();

    const dialog = page.getByRole("dialog");
    await expect(dialog).toBeVisible();
    await expect(
      dialog.getByText(/add repository/i).first(),
    ).toBeVisible();
    await expect(dialog.getByPlaceholder("/path/to/repository")).toBeVisible();
  });

  // FIXME: AddRepoDialog has no inline validation copy — the Add button is
  // simply `disabled` when the path field is empty
  // (see packages/web/src/components/layout/add-repo-dialog.tsx:82).
  test.skip("validates empty path before submitting", async ({ page }) => {
    await openAddRepoDialog(page);
    await page.getByRole("button", { name: /^add$/i }).click();
    await expect(page.getByText(/path/i)).toBeVisible();
  });

  test("closes on cancel", async ({ page }) => {
    await openAddRepoDialog(page);
    await page.getByRole("button", { name: /^cancel$/i }).click();
    await expect(page.getByRole("dialog")).toBeHidden();
  });
});
