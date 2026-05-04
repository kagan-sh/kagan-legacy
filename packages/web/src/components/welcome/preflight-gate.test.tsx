import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, act, fireEvent } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { renderWithProviders } from '@/test/render';
import type { DoctorReportResponse } from '@kagan/shared-api-client';

// ---------------------------------------------------------------------------
// Mock apiClient before importing the component under test
// ---------------------------------------------------------------------------

vi.mock('@/lib/api/client', () => ({
  apiClient: {
    getDoctorReport: vi.fn(),
  },
}));

const { PreflightGate } = await import('@/components/welcome/preflight-gate');
const { apiClient } = await import('@/lib/api/client');

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

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

// Clipboard mock — jsdom's Clipboard object exists but throws in tests.
// We create a fresh mock each beforeEach AFTER clearAllMocks so it isn't wiped.
let writeTextMock: ReturnType<typeof vi.fn>;

beforeEach(() => {
  vi.clearAllMocks();
  // Stable default: server is healthy
  (apiClient.getDoctorReport as ReturnType<typeof vi.fn>).mockResolvedValue(makeReport());

  // Re-create clipboard mock after clearAllMocks.
  // userEvent.setup() (called in some tests) installs a getter directly on navigator,
  // which shadows prototype-level mocks. Override on navigator directly to win.
  writeTextMock = vi.fn().mockResolvedValue(undefined);
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText: writeTextMock },
    writable: true,
    configurable: true,
  });
});

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('PreflightGate', () => {
  it('renders nothing when all checks pass (all-green state)', async () => {
    (apiClient.getDoctorReport as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeReport({ ok: true, fail_count: 0, warn_count: 0 }),
    );

    const { container } = renderGate();

    // Wait for the async effect to resolve
    await waitFor(() => {
      expect(apiClient.getDoctorReport).toHaveBeenCalledOnce();
    });

    // No banner, no dialog
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(container.firstChild).toBeNull();
  });

  it('calls getDoctorReport via apiClient exactly once on mount', async () => {
    renderGate();

    await waitFor(() => {
      expect(apiClient.getDoctorReport).toHaveBeenCalledOnce();
    });
  });

  it('renders an amber Alert in the degraded (WARN-only) state listing WARN check names', async () => {
    (apiClient.getDoctorReport as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeReport({
        ok: false,
        fail_count: 0,
        warn_count: 2,
        checks: [
          {
            name: 'optional-tool',
            status: 'WARN',
            message: 'Tool not found',
            fix_hint: 'brew install optional-tool',
            verify_hint: 'optional-tool --version',
            category: 'tools',
            is_blocking: false,
          },
          {
            name: 'another-tool',
            status: 'WARN',
            message: 'Not installed',
            fix_hint: 'pip install another-tool',
            verify_hint: 'another-tool --help',
            category: 'tools',
            is_blocking: false,
          },
        ],
      }),
    );

    renderGate();

    const alert = await screen.findByRole('alert');
    expect(alert).toBeInTheDocument();

    // Both WARN check names should appear
    expect(screen.getByText('optional-tool')).toBeInTheDocument();
    expect(screen.getByText('another-tool')).toBeInTheDocument();

    // No dialog
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
  });

  it('dismissing the degraded alert hides it for the session (no reload)', async () => {
    (apiClient.getDoctorReport as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeReport({
        ok: false,
        fail_count: 0,
        warn_count: 1,
        checks: [
          {
            name: 'optional-tool',
            status: 'WARN',
            message: 'Tool not found',
            fix_hint: 'brew install optional-tool',
            verify_hint: 'optional-tool --version',
            category: 'tools',
            is_blocking: false,
          },
        ],
      }),
    );

    const user = userEvent.setup();
    renderGate();

    const alert = await screen.findByRole('alert');
    expect(alert).toBeInTheDocument();

    const dismissButton = screen.getByRole('button', { name: /dismiss/i });
    await user.click(dismissButton);

    // Alert should be gone; getDoctorReport not called again
    await waitFor(() => {
      expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    });
    expect(apiClient.getDoctorReport).toHaveBeenCalledOnce();
  });

  it('renders a non-dismissible Dialog in the zero-ready (FAIL) state', async () => {
    (apiClient.getDoctorReport as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeReport({
        ok: false,
        fail_count: 1,
        warn_count: 0,
        checks: [
          {
            name: 'critical-dep',
            status: 'FAIL',
            message: 'Dependency missing',
            fix_hint: 'apt-get install critical-dep',
            verify_hint: 'critical-dep --version',
            category: 'deps',
            is_blocking: true,
          },
        ],
      }),
    );

    renderGate();

    const dialog = await screen.findByRole('dialog');
    expect(dialog).toBeInTheDocument();
    expect(dialog).toHaveAttribute('aria-modal', 'true');

    // aria-labelledby must point to the dialog title
    const labelledById = dialog.getAttribute('aria-labelledby');
    expect(labelledById).toBeTruthy();
    const titleEl = document.getElementById(labelledById!);
    expect(titleEl).toBeInTheDocument();
    expect(titleEl?.textContent).toMatch(/setup required/i);

    // No close button
    expect(screen.queryByRole('button', { name: /close/i })).not.toBeInTheDocument();

    // No degraded banner alongside it
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
  });

  it('shows name, message, and fix_hint with copy button for each FAIL/WARN check in the dialog', async () => {
    (apiClient.getDoctorReport as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeReport({
        ok: false,
        fail_count: 1,
        warn_count: 1,
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
          {
            name: 'optional-feature',
            status: 'WARN',
            message: 'Feature unavailable',
            fix_hint: 'pip install optional-feature',
            verify_hint: 'optional-feature --help',
            category: 'features',
            is_blocking: false,
          },
        ],
      }),
    );

    renderGate();

    await screen.findByRole('dialog');

    // Both check names
    expect(screen.getByText('missing-tool')).toBeInTheDocument();
    expect(screen.getByText('optional-feature')).toBeInTheDocument();

    // Both messages
    expect(screen.getByText('Tool is missing')).toBeInTheDocument();
    expect(screen.getByText('Feature unavailable')).toBeInTheDocument();

    // fix_hint rendered in <code>
    expect(screen.getByText('brew install missing-tool')).toBeInTheDocument();
    expect(screen.getByText('pip install optional-feature')).toBeInTheDocument();

    // Copy buttons exist (one per check with a fix_hint)
    const copyButtons = screen.getAllByRole('button', { name: /copy fix hint/i });
    expect(copyButtons).toHaveLength(2);
  });

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

    // userEvent.setup() (used in sibling tests) installs a getter on navigator
    // directly (not on its prototype), shadowing prototype-level clipboard mocks.
    // We override it on navigator directly with a value descriptor to shadow the getter.
    const clipboardMock = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: clipboardMock },
      writable: true,
      configurable: true,
    });

    // Use fireEvent.click to avoid userEvent re-installing its clipboard handler
    fireEvent.click(copyButton);

    expect(clipboardMock).toHaveBeenCalledWith('brew install missing-tool');

    // "Copied" confirmation label appears
    await waitFor(() => {
      expect(screen.getByText('Copied')).toBeInTheDocument();
    });
  });

  it('renders nothing on network error (silently degrades)', async () => {
    (apiClient.getDoctorReport as ReturnType<typeof vi.fn>).mockRejectedValue(
      new Error('Network error'),
    );

    const { container } = renderGate();

    await waitFor(() => {
      expect(apiClient.getDoctorReport).toHaveBeenCalledOnce();
    });

    // On error: no banner, no dialog, no crash
    expect(screen.queryByRole('alert')).not.toBeInTheDocument();
    expect(screen.queryByRole('dialog')).not.toBeInTheDocument();
    expect(container.firstChild).toBeNull();
  });

  it('does not call getDoctorReport again when component re-renders', async () => {
    (apiClient.getDoctorReport as ReturnType<typeof vi.fn>).mockResolvedValue(
      makeReport({ ok: true }),
    );

    const { rerender } = renderGate();

    await waitFor(() => {
      expect(apiClient.getDoctorReport).toHaveBeenCalledOnce();
    });

    // Force a re-render (same component)
    await act(async () => {
      rerender(
        <PreflightGate />,
      );
    });

    // Still only called once
    expect(apiClient.getDoctorReport).toHaveBeenCalledOnce();
  });
});
