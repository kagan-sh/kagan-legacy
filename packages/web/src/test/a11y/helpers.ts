import { expect } from 'vitest';
import { axe, type AxeMatchers } from 'vitest-axe';

/**
 * Run axe on a container and return violations + serious incomplete checks.
 * Used by page-level a11y tests to produce a baseline-friendly count
 * without hard-failing when legacy components regress.
 */
export async function collectViolations(container: HTMLElement) {
  const results = await axe(container);
  const isJsdomFalsePositive = (item: (typeof results.incomplete)[number]) => {
    const checks = item.nodes.flatMap((n) => [...n.any, ...n.all, ...n.none]);
    if (item.id === 'color-contrast' && checks.some((c) => c.id === 'error-occurred')) return true;
    if (
      item.id === 'aria-valid-attr-value' &&
      checks.every((c) => (c.data as Record<string, unknown>)?.messageKey === 'controlsWithinPopup')
    ) {
      return true;
    }
    return false;
  };
  const seriousIncomplete = results.incomplete.filter(
    (item) =>
      (item.impact === 'serious' || item.impact === 'critical') && !isJsdomFalsePositive(item),
  );
  return { results, seriousIncomplete };
}

/** Strict pass: zero violations + zero serious incomplete. */
export async function expectNoViolations(container: HTMLElement) {
  const { results, seriousIncomplete } = await collectViolations(container);
  (expect(results) as unknown as AxeMatchers).toHaveNoViolations();
  expect(seriousIncomplete).toEqual([]);
}
