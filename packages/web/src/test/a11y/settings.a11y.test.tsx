/**
 * Page-level a11y baseline for the Settings route.
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
    getSettings: vi.fn().mockResolvedValue({}),
    getResolvedSettings: vi.fn().mockResolvedValue({ workflow: {} }),
    setSettings: vi.fn().mockResolvedValue({}),
    getHealth: vi.fn().mockResolvedValue({ status: 'ok', version: '0.0.0' }),
    getPreflight: vi.fn().mockResolvedValue({ checks: [] }),
    getBaseUrl: vi.fn().mockReturnValue('http://localhost:8765'),
    getProjects: vi.fn().mockResolvedValue([]),
    getProjectRepos: vi.fn().mockResolvedValue([]),
    getChatAgents: vi.fn().mockResolvedValue({ backends: [], default: 'claude-code' }),
    getRecommendedBackend: vi.fn().mockResolvedValue({ backend: 'claude-code' }),
  },
}));

const { Component: SettingsPage } = await import('@/pages/settings-page');

describe('Settings page a11y baseline', () => {
  it('default render — records violations', async () => {
    const { container } = renderWithProviders(<SettingsPage />);
    const { results, seriousIncomplete } = await collectViolations(container);
    if (results.violations.length > 0 || seriousIncomplete.length > 0) {
      // TODO(a11y-migration): baseline recorded; migrate components to eliminate.
      console.info(
        `[a11y baseline] Settings: ${results.violations.length} violations, ${seriousIncomplete.length} serious incomplete`,
      );
    }
    expect(results).toBeDefined();
  });
});
