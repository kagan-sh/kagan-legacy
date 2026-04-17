/**
 * Page-level a11y test for the Analytics route.
 * Strict: fails if any violations or serious incomplete checks are reported.
 */
import { describe, it, vi } from 'vitest';
import { renderWithProviders } from '@/test/render';
import { expectNoViolations } from '@/test/a11y/helpers';

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

describe('Analytics page a11y', () => {
  it('default render — has no violations', async () => {
    const { container } = renderWithProviders(<AnalyticsPage />);
    await expectNoViolations(container);
  });
});
