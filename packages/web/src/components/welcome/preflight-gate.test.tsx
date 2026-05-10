import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, act, fireEvent } from '@testing-library/react';
import { renderWithProviders } from '@/test/render';
import type { DoctorReportResponse } from '@kagan/shared-api-client';

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    getDoctorReport: vi.fn(),
  },
}));

const { PreflightGate } = await import('@/components/welcome/preflight-gate');
const { apiClient } = await import('@/lib/api/client');

function makeReport(overrides: Partial<DoctorReportResponse> = {}): DoctorReportResponse {
  return {
    checks: [],
    ok: true,
    fail_count: 0,
    warn_count: 0,
    ...overrides,
  };
}

function renderGate() {
  return renderWithProviders(<PreflightGate />);
}

let writeTextMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
  (apiClient.getDoctorReport as ReturnType<typeof vi.fn>).mockResolvedValue(makeReport());

  writeTextMock = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText: writeTextMock },
    writable: true,
    configurable: true,
  });
});

describe('PreflightGate — contract tests', () => {
  it('renders lowercase fail/warn statuses from the API contract', async () => {
    (apiClient.getDoctorReport as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeReport({
        ok: false,
        fail_count: 1,
        warn_count: 1,
        checks: [
          {
            name: 'agent backends',
            status: 'fail',
            message: 'Default backend not found',
            fix_hint: 'kg doctor',
            verify_hint: 'which codex',
            category: 'backend',
            is_blocking: true,
          },
          {
            name: 'gh cli',
            status: 'warn',
            message: 'GitHub CLI not found',
            fix_hint: 'brew install gh',
            verify_hint: 'gh --version',
            category: 'integration',
            is_blocking: false,
          },
        ],
      }),
    );

    renderGate();

    await screen.findByRole('dialog');
    expect(screen.getByText('agent backends')).toBeInTheDocument();
    expect(screen.getByText('gh cli')).toBeInTheDocument();
  });

  it('copy button writes fix_hint to clipboard and shows transient Copied confirmation', async () => {
    (apiClient.getDoctorReport as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeReport({
        ok: false,
        fail_count: 1,
        warn_count: 0,
        checks: [
          {
            name: 'missing-tool',
            status: 'FAIL',
            message: 'Tool is missing',
            fix_hint: 'brew install missing-tool',
            verify_hint: 'missing-tool --version',
            category: 'tools',
            is_blocking: true,
          },
        ],
      }),
    );

    renderGate();
    await screen.findByRole('dialog');

    const copyButton = screen.getByRole('button', { name: /copy fix hint/i });

    const clipboardMock = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: clipboardMock },
      writable: true,
      configurable: true,
    });

    fireEvent.click(copyButton);

    expect(clipboardMock).toHaveBeenCalledWith('brew install missing-tool');

    await waitFor(() => {
      expect(screen.getByText('Copied')).toBeInTheDocument();
    });
  });

  it('does not call getDoctorReport again when component re-renders', async () => {
    (apiClient.getDoctorReport as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeReport({ ok: true }),
    );

    const { rerender } = renderGate();

    await waitFor(() => {
      expect(apiClient.getDoctorReport).toHaveBeenCalledOnce();
    });

    await act(async () => {
      rerender(<PreflightGate />);
    });

    expect(apiClient.getDoctorReport).toHaveBeenCalledOnce();
  });
});
