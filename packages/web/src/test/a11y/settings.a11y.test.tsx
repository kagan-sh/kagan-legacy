/**
 * Page-level a11y test for the Settings route.
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

describe('Settings page a11y', () => {
  it('default render — has no violations', async () => {
    const { container } = renderWithProviders(<SettingsPage />);
    await expectNoViolations(container);
  });
});
