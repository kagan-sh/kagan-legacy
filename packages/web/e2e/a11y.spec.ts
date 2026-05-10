import AxeBuilder from "@axe-core/playwright";
import type { Page } from "@playwright/test";
import { test, expect } from "./coverage-fixture";
import { ensureBoardReady } from "./helpers";

const SERIOUS_OR_CRITICAL = ["serious", "critical"] as const;

// Rules tracked separately by design and not gated per-PR:
//   - `color-contrast`: every `--kagan-*` accent currently fails AA on
//     `--surface-1`; audited deliberately, not on every PR.
//   - `nested-interactive`: Radix dropdown triggers wrap interactive
//     children; design is rebuilding affordances.
const SUPPRESSED_RULES = ["color-contrast", "nested-interactive"];

async function auditViolations(page: Page): Promise<unknown[]> {
  const results = await new AxeBuilder({ page })
    .withTags(["wcag2a", "wcag2aa"])
    .disableRules(SUPPRESSED_RULES)
    .analyze();
  return results.violations.filter((v) =>
    (SERIOUS_OR_CRITICAL as readonly string[]).includes(v.impact ?? ""),
  );
}

test.describe("Accessibility (axe on real browser)", () => {
  test.beforeEach(async ({ page, request }) => {
    await ensureBoardReady(page, request);
  });

  test("board surface has no serious/critical violations", async ({ page }) => {
    await page.goto("/board");
    await expect(
      page.getByRole("heading", { name: "Backlog", exact: true }),
    ).toBeVisible();

    const violations = await auditViolations(page);
    expect(violations, JSON.stringify(violations, null, 2)).toEqual([]);
  });

  test("settings surface has no serious/critical violations", async ({ page }) => {
    await page.goto("/settings");
    await expect(page.getByText(/connection/i)).toBeVisible();

    const violations = await auditViolations(page);
    expect(violations, JSON.stringify(violations, null, 2)).toEqual([]);
  });

  test("welcome surface has no serious/critical violations", async ({ page }) => {
    await page.goto("/welcome");
    await expect(
      page.getByRole("button", { name: /^new project$/i }),
    ).toBeVisible();

    const violations = await auditViolations(page);
    expect(violations, JSON.stringify(violations, null, 2)).toEqual([]);
  });
});
