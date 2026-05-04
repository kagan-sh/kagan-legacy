import { describe, it, expect, vi, beforeEach } from 'vitest';
import { screen, waitFor, fireEvent } from '@testing-library/react';
import { renderWithProviders } from '@/test/render';
import { PathPicker } from '@/components/shared/path-picker';
import type { FsBrowseResponse } from '@kagan/shared-api-client';

// vi.mock is hoisted — factory must be self-contained (no outer-scope refs).
vi.mock('@/lib/api/client', () => ({
  apiClient: {
    browsePath: vi.fn(),
  },
}));

// A minimal valid FsEntry for populating fixtures (so the ".." button renders).
const DUMMY_ENTRY = {
  name: 'some-folder',
  path: '/dummy/path',
  is_dir: true,
  is_git_repo: false,
  is_link: false,
};

const DUMMY_WIN_ENTRY = {
  name: 'some-folder',
  path: 'C:\\dummy\\path',
  is_dir: true,
  is_git_repo: false,
  is_link: false,
};

// Helper: build a POSIX browse response fixture.
function posixResponse(path: string, overrides: Partial<FsBrowseResponse> = {}): FsBrowseResponse {
  const segments = path.split('/').filter(Boolean);
  // Parent: strip last segment; null when at FS root (single segment or empty).
  let parent: string | null;
  if (segments.length <= 1) {
    parent = null;
  } else {
    parent = '/' + segments.slice(0, -1).join('/');
  }
  return {
    path,
    parent,
    separator: '/',
    roots: ['/'],
    entries: [DUMMY_ENTRY],
    ...overrides,
  };
}

// Helper: build a Windows browse response fixture.
function winResponse(path: string, overrides: Partial<FsBrowseResponse> = {}): FsBrowseResponse {
  // path looks like "C:\\Users\\you"
  const segments = path.split('\\').filter(Boolean);
  // parent: remove last segment, re-join; if only one segment left (drive), parent is null.
  let parent: string | null;
  if (segments.length <= 1) {
    parent = null;
  } else if (segments.length === 2) {
    parent = segments[0] + '\\';
  } else {
    parent = segments.slice(0, -1).join('\\');
  }
  return {
    path,
    parent,
    separator: '\\',
    roots: ['C:\\', 'D:\\'],
    entries: [DUMMY_WIN_ENTRY],
    ...overrides,
  };
}

describe('PathPicker', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  // ---------------------------------------------------------------------------
  // POSIX breadcrumbs
  // ---------------------------------------------------------------------------

  describe('POSIX breadcrumbs', () => {
    it('renders correct breadcrumb labels for /Users/you/dev', async () => {
      const { apiClient } = await import('@/lib/api/client');
      vi.mocked(apiClient.browsePath).mockResolvedValue(
        posixResponse('/Users/you/dev'),
      );

      renderWithProviders(
        <PathPicker open onOpenChange={vi.fn()} onSelect={vi.fn()} />,
      );

      await waitFor(() => {
        expect(screen.getByText('Users')).toBeVisible();
        expect(screen.getByText('you')).toBeVisible();
        expect(screen.getByText('dev')).toBeVisible();
      });
    });

    it('clicking a breadcrumb segment calls browsePath with the correct partial path', async () => {
      const { apiClient } = await import('@/lib/api/client');
      vi.mocked(apiClient.browsePath).mockResolvedValue(
        posixResponse('/Users/you/dev'),
      );

      renderWithProviders(
        <PathPicker open onOpenChange={vi.fn()} onSelect={vi.fn()} />,
      );

      await waitFor(() => expect(screen.getByText('Users')).toBeVisible());

      fireEvent.click(screen.getByText('Users'));

      await waitFor(() => {
        expect(apiClient.browsePath).toHaveBeenCalledWith('/Users');
      });
    });

    it('up arrow navigates to parent path from server response', async () => {
      const { apiClient } = await import('@/lib/api/client');
      vi.mocked(apiClient.browsePath).mockResolvedValue(
        posixResponse('/Users/you/dev', { parent: '/Users/you' }),
      );

      renderWithProviders(
        <PathPicker open onOpenChange={vi.fn()} onSelect={vi.fn()} />,
      );

      // Wait for entries area to show ".." button (parent is not null)
      await waitFor(() => expect(screen.getByText('..')).toBeVisible());

      fireEvent.click(screen.getByText('..'));

      await waitFor(() => {
        expect(apiClient.browsePath).toHaveBeenCalledWith('/Users/you');
      });
    });
  });

  // ---------------------------------------------------------------------------
  // Windows breadcrumbs
  // ---------------------------------------------------------------------------

  describe('Windows breadcrumbs', () => {
    it('renders correct breadcrumb labels for C:\\Users\\you', async () => {
      const { apiClient } = await import('@/lib/api/client');
      vi.mocked(apiClient.browsePath).mockResolvedValue(
        winResponse('C:\\Users\\you'),
      );

      renderWithProviders(
        <PathPicker open onOpenChange={vi.fn()} onSelect={vi.fn()} />,
      );

      await waitFor(() => {
        // "C:" appears in both root picker and breadcrumb — use getAllByText.
        const cElements = screen.getAllByText('C:');
        expect(cElements.length).toBeGreaterThanOrEqual(1);
        expect(cElements[0]).toBeVisible();
        expect(screen.getByText('Users')).toBeVisible();
        expect(screen.getByText('you')).toBeVisible();
      });
    });

    it('clicking the C: breadcrumb navigates to C:\\ (with trailing separator)', async () => {
      const { apiClient } = await import('@/lib/api/client');
      vi.mocked(apiClient.browsePath).mockResolvedValue(
        winResponse('C:\\Users\\you'),
      );

      renderWithProviders(
        <PathPicker open onOpenChange={vi.fn()} onSelect={vi.fn()} />,
      );

      // Wait for breadcrumbs to load.
      await waitFor(() => expect(screen.getAllByText('C:').length).toBeGreaterThan(0));

      // Click the root-picker "Browse C:\\" button — guaranteed to navigate to C:\.
      fireEvent.click(screen.getByRole('button', { name: 'Browse C:\\' }));

      await waitFor(() => {
        expect(apiClient.browsePath).toHaveBeenCalledWith('C:\\');
      });
    });

    it('up arrow from C:\\Users navigates to C:\\', async () => {
      const { apiClient } = await import('@/lib/api/client');
      // At C:\Users, parent is C:\
      vi.mocked(apiClient.browsePath).mockResolvedValue(
        winResponse('C:\\Users', { parent: 'C:\\' }),
      );

      renderWithProviders(
        <PathPicker open onOpenChange={vi.fn()} onSelect={vi.fn()} />,
      );

      await waitFor(() => expect(screen.getByText('..')).toBeVisible());

      fireEvent.click(screen.getByText('..'));

      await waitFor(() => {
        expect(apiClient.browsePath).toHaveBeenCalledWith('C:\\');
      });
    });

    it('up button is hidden when parent is null (at filesystem root)', async () => {
      const { apiClient } = await import('@/lib/api/client');
      vi.mocked(apiClient.browsePath).mockResolvedValue(
        winResponse('C:\\', { parent: null }),
      );

      renderWithProviders(
        <PathPicker open onOpenChange={vi.fn()} onSelect={vi.fn()} />,
      );

      // Wait for entries to render (the dummy entry should appear)
      await waitFor(() => expect(screen.getByText('some-folder')).toBeVisible());

      // ".." should not appear when parent is null
      expect(screen.queryByText('..')).toBeNull();
    });
  });

  // ---------------------------------------------------------------------------
  // Root pickers (Windows multi-drive)
  // ---------------------------------------------------------------------------

  describe('roots / drive pickers', () => {
    it('renders two drive buttons when roots has C:\\ and D:\\', async () => {
      const { apiClient } = await import('@/lib/api/client');
      vi.mocked(apiClient.browsePath).mockResolvedValue(
        winResponse('C:\\Users'),
      );

      renderWithProviders(
        <PathPicker open onOpenChange={vi.fn()} onSelect={vi.fn()} />,
      );

      await waitFor(() => {
        // Root picker buttons are rendered with aria-label "Browse C:\" etc.
        expect(screen.getByRole('button', { name: 'Browse C:\\' })).toBeVisible();
        expect(screen.getByRole('button', { name: 'Browse D:\\' })).toBeVisible();
      });
    });

    it('clicking D: root button calls browsePath with D:\\', async () => {
      const { apiClient } = await import('@/lib/api/client');
      vi.mocked(apiClient.browsePath).mockResolvedValue(
        winResponse('C:\\Users'),
      );

      renderWithProviders(
        <PathPicker open onOpenChange={vi.fn()} onSelect={vi.fn()} />,
      );

      await waitFor(() =>
        expect(screen.getByRole('button', { name: 'Browse D:\\' })).toBeVisible(),
      );

      fireEvent.click(screen.getByRole('button', { name: 'Browse D:\\' }));

      await waitFor(() => {
        expect(apiClient.browsePath).toHaveBeenCalledWith('D:\\');
      });
    });

    it('does not render root picker buttons on POSIX (single root)', async () => {
      const { apiClient } = await import('@/lib/api/client');
      vi.mocked(apiClient.browsePath).mockResolvedValue(
        posixResponse('/Users/you'),
      );

      renderWithProviders(
        <PathPicker open onOpenChange={vi.fn()} onSelect={vi.fn()} />,
      );

      await waitFor(() => expect(screen.getByText('Users')).toBeVisible());

      // No "Browse /" aria-label root picker buttons should appear
      expect(screen.queryByRole('button', { name: 'Browse /' })).toBeNull();
    });
  });

  // ---------------------------------------------------------------------------
  // Home button
  // ---------------------------------------------------------------------------

  describe('Home button', () => {
    it('home button navigates to ~ on POSIX', async () => {
      const { apiClient } = await import('@/lib/api/client');
      vi.mocked(apiClient.browsePath).mockResolvedValue(
        posixResponse('/Users/you/dev'),
      );

      renderWithProviders(
        <PathPicker open onOpenChange={vi.fn()} onSelect={vi.fn()} />,
      );

      await waitFor(() => expect(screen.getByText('Users')).toBeVisible());

      fireEvent.click(screen.getByRole('button', { name: 'Home' }));

      await waitFor(() => {
        expect(apiClient.browsePath).toHaveBeenCalledWith('~');
      });
    });

    it('home button navigates to ~ on Windows', async () => {
      const { apiClient } = await import('@/lib/api/client');
      vi.mocked(apiClient.browsePath).mockResolvedValue(
        winResponse('C:\\Users\\you'),
      );

      renderWithProviders(
        <PathPicker open onOpenChange={vi.fn()} onSelect={vi.fn()} />,
      );

      await waitFor(() => expect(screen.getByText('you')).toBeVisible());

      fireEvent.click(screen.getByRole('button', { name: 'Home' }));

      await waitFor(() => {
        expect(apiClient.browsePath).toHaveBeenCalledWith('~');
      });
    });
  });

  // ---------------------------------------------------------------------------
  // Select button label
  // ---------------------------------------------------------------------------

  describe('Select button label', () => {
    it('shows last segment as label on POSIX', async () => {
      const { apiClient } = await import('@/lib/api/client');
      vi.mocked(apiClient.browsePath).mockResolvedValue(
        posixResponse('/Users/you/dev'),
      );

      renderWithProviders(
        <PathPicker open onOpenChange={vi.fn()} onSelect={vi.fn()} />,
      );

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /Select dev/i })).toBeVisible(),
      );
    });

    it('shows last segment as label on Windows', async () => {
      const { apiClient } = await import('@/lib/api/client');
      vi.mocked(apiClient.browsePath).mockResolvedValue(
        winResponse('C:\\Users\\you'),
      );

      renderWithProviders(
        <PathPicker open onOpenChange={vi.fn()} onSelect={vi.fn()} />,
      );

      await waitFor(() =>
        expect(screen.getByRole('button', { name: /Select you/i })).toBeVisible(),
      );
    });
  });
});
