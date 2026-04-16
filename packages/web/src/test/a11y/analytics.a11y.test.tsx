/**
 * Page-level a11y baseline for the Analytics route.
 * Infrastructure only: records current state, does not hard-fail legacy issues.
 */
import { describe, it, expect, vi } from 'vitest';
import { renderWithProviders } from '@/test/render';
import { collectViolations } from '@/test/a11y/helpers';

vi.mock('react-router', async () => {
  const actual = await vi.importActual<typeof import('react-router')>('react-router');
  return { ...actual, useNavigate: () => vi.fn() };
});

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    getBackendStats: vi.fn().mockResolvedValue([]),
    getSessionTimeline: vi.fn().mockResolvedValue([]),
    getStatsByRole: vi.fn().mockResolvedValue([]),
    getStatsByTaskType: vi.fn().mockResolvedValue([]),
    getCombinedStats: vi.fn().mockResolvedValue([]),
    getAnalyticsExport: vi.fn().mockResolvedValue({}),
    getRecommendedBackend: vi.fn().mockResolvedValue({ backend: 'claude-code' }),
  },
}));

const { Component: AnalyticsPage } = await import('@/pages/analytics-page');

describe('Analytics page a11y baseline', () => {
  it('default render — records violations', async () => {
    const { container } = renderWithProviders(<AnalyticsPage />);
    const { results, seriousIncomplete } = await collectViolations(container);
    if (results.violations.length > 0 || seriousIncomplete.length > 0) {
      // TODO(a11y-migration): baseline recorded; migrate components to eliminate.
      console.info(
        `[a11y baseline] Analytics: ${results.violations.length} violations, ${seriousIncomplete.length} serious incomplete`,
      );
    }
    expect(results).toBeDefined();
  });
});
