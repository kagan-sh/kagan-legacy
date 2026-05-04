import { describe, it, expect, vi } from 'vitest';
import { screen } from '@testing-library/react';
import { createStore } from 'jotai';
import { renderWithProviders } from '@/test/render';
import { ArtifactsPanel } from '@/components/ArtifactsPanel';
import { artifactsAtom, type Artifact } from '@/lib/atoms/artifacts';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function makeArtifact(overrides: Partial<Artifact> = {}): Artifact {
  return {
    id: `artifact-${Math.random().toString(36).slice(2, 8)}`,
    type: 'html',
    content: '<p>hello</p>',
    ...overrides,
  };
}

function renderPanel(
  artifacts: Artifact[],
  { open = true, onClose = vi.fn() }: { open?: boolean; onClose?: () => void } = {},
) {
  const store = createStore();
  store.set(artifactsAtom, artifacts);
  return renderWithProviders(<ArtifactsPanel open={open} onClose={onClose} />, { store });
}

// ---------------------------------------------------------------------------
// Tests
// ---------------------------------------------------------------------------

describe('ArtifactsPanel', () => {
  it('renders nothing when open is false', () => {
    const { container } = renderPanel([makeArtifact()], { open: false });
    expect(container.firstChild).toBeNull();
  });

  it('renders nothing when the artifact list is empty', () => {
    const { container } = renderPanel([], { open: true });
    expect(container.firstChild).toBeNull();
  });

  it('renders one tab per artifact entry', () => {
    const a1 = makeArtifact({ title: 'Page A', type: 'html' });
    const a2 = makeArtifact({ title: 'Diagram B', type: 'svg' });
    renderPanel([a1, a2]);

    expect(screen.getByRole('tab', { name: 'Page A' })).toBeTruthy();
    expect(screen.getByRole('tab', { name: 'Diagram B' })).toBeTruthy();
  });

  it('HTML artifact uses a sandboxed iframe with sandbox="" attribute', () => {
    const { container } = renderPanel([makeArtifact({ type: 'html', content: '<b>bold</b>' })]);
    const iframes = container.querySelectorAll('iframe[sandbox=""]');
    expect(iframes.length).toBeGreaterThanOrEqual(1);
  });

  it('SVG artifact uses a sandboxed iframe with sandbox="" attribute', () => {
    const { container } = renderPanel([
      makeArtifact({ type: 'svg', content: '<svg><circle cx="5" cy="5" r="5"/></svg>' }),
    ]);
    const iframes = container.querySelectorAll('iframe[sandbox=""]');
    expect(iframes.length).toBeGreaterThanOrEqual(1);
  });

  it('iframes do not have allow-scripts in the sandbox attribute', () => {
    const { container } = renderPanel([makeArtifact({ type: 'html' })]);
    const iframes = container.querySelectorAll('iframe');
    for (const iframe of iframes) {
      const sandbox = iframe.getAttribute('sandbox') ?? '';
      expect(sandbox).not.toContain('allow-scripts');
      expect(sandbox).not.toContain('allow-same-origin');
    }
  });

  it('markdown artifact renders prose content without an iframe', () => {
    const { container } = renderPanel([
      makeArtifact({ type: 'markdown', content: '# Hello' }),
    ]);
    // No iframe for markdown
    expect(container.querySelectorAll('iframe').length).toBe(0);
  });

  it('close button calls onClose', () => {
    const onClose = vi.fn();
    renderPanel([makeArtifact()], { onClose });
    const closeBtn = screen.getByRole('button', { name: 'Close artifacts panel' });
    closeBtn.click();
    expect(onClose).toHaveBeenCalledOnce();
  });

  describe('D3: ARIA tab pattern', () => {
    it('tab container has role="tablist"', () => {
      renderPanel([makeArtifact({ title: 'Tab One' })]);
      expect(screen.getByRole('tablist')).toBeTruthy();
    });

    it('each tab button has role="tab"', () => {
      renderPanel([
        makeArtifact({ title: 'First' }),
        makeArtifact({ title: 'Second' }),
      ]);
      const tabs = screen.getAllByRole('tab');
      expect(tabs).toHaveLength(2);
    });

    it('active tab has aria-selected="true"', () => {
      const a = makeArtifact({ title: 'Active Tab' });
      renderPanel([a]);
      const tab = screen.getByRole('tab', { name: 'Active Tab' });
      expect(tab).toHaveAttribute('aria-selected', 'true');
    });

    it('inactive tab has aria-selected="false"', () => {
      const a1 = makeArtifact({ title: 'Tab A' });
      const a2 = makeArtifact({ title: 'Tab B' });
      renderPanel([a1, a2]);
      // Last artifact is auto-selected; first is inactive.
      const firstTab = screen.getByRole('tab', { name: 'Tab A' });
      expect(firstTab).toHaveAttribute('aria-selected', 'false');
    });

    it('content area has role="tabpanel"', () => {
      renderPanel([makeArtifact({ title: 'Panel' })]);
      expect(screen.getByRole('tabpanel')).toBeTruthy();
    });

    it('active tab aria-controls matches tabpanel id', () => {
      const a = makeArtifact({ title: 'Linked' });
      renderPanel([a]);
      const tab = screen.getByRole('tab', { name: 'Linked' });
      const panelId = tab.getAttribute('aria-controls');
      expect(panelId).toBeTruthy();
      const panel = document.getElementById(panelId!);
      expect(panel).toBeTruthy();
    });
  });
});
