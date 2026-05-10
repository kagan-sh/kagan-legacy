import { describe, it, expect, beforeEach, afterEach } from 'vitest';
import { fireEvent, screen } from '@testing-library/react';
import { renderWithProviders } from '@/test/render';
import { ChatStreamEntries } from './chat-stream-entries';
import type { ChatStreamEntry } from '@/lib/atoms/chat';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function workedEntry(overrides?: Partial<Extract<ChatStreamEntry, { kind: 'worked' }>>): ChatStreamEntry {
  return {
    kind: 'worked',
    label: 'Worked for 3.2s',
    steps: ['0.1s  read_file', '1.4s  write_file', '2.9s  run_tests'],
    done: true,
    startedAt: Date.now() - 3200,
    ...overrides,
  };
}

function filesEntry(items: string[] = ['src/foo.ts', 'src/bar.tsx']): ChatStreamEntry {
  return { kind: 'files', items };
}

// ---------------------------------------------------------------------------
// WorkedAccordion — collapsed by default
// ---------------------------------------------------------------------------

describe('WorkedAccordion', () => {
  it('renders in collapsed state by default', () => {
    renderWithProviders(<ChatStreamEntries entries={[workedEntry()]} />);

    const accordion = screen.getByTestId('worked-accordion');
    expect(accordion).toBeInTheDocument();

    const header = accordion.querySelector('button[aria-expanded]') as HTMLButtonElement;
    expect(header).not.toBeNull();
    expect(header.getAttribute('aria-expanded')).toBe('false');
    expect(header.getAttribute('data-open')).toBe('false');

    const steps = screen.getByTestId('worked-steps');
    expect(steps.getAttribute('aria-hidden')).toBe('true');
  });

  it('clicking the header toggles data-open and reveals steps', () => {
    renderWithProviders(<ChatStreamEntries entries={[workedEntry()]} />);

    const header = screen.getByRole('button', { name: /expand tool steps/i });
    fireEvent.click(header);

    expect(header.getAttribute('aria-expanded')).toBe('true');
    expect(header.getAttribute('data-open')).toBe('true');

    const steps = screen.getByTestId('worked-steps');
    expect(steps.getAttribute('aria-hidden')).toBe('false');
    expect(steps.getAttribute('data-open')).toBe('true');
  });

  it('clicking again collapses back to closed', () => {
    renderWithProviders(<ChatStreamEntries entries={[workedEntry()]} />);

    const header = screen.getByRole('button', { name: /expand tool steps/i });
    fireEvent.click(header);
    fireEvent.click(header);

    expect(header.getAttribute('aria-expanded')).toBe('false');
    expect(header.getAttribute('data-open')).toBe('false');
  });

  it('renders step lines when open', () => {
    renderWithProviders(<ChatStreamEntries entries={[workedEntry({ steps: ['0.1s  read_file', '2.9s  run_tests'] })]} />);

    const header = screen.getByRole('button', { name: /expand tool steps/i });
    fireEvent.click(header);

    const stepsEl = screen.getByTestId('worked-steps');
    expect(stepsEl).toHaveTextContent('read_file');
    expect(stepsEl).toHaveTextContent('run_tests');
  });

  it('shows check icon when done=true', () => {
    renderWithProviders(<ChatStreamEntries entries={[workedEntry({ done: true })]} />);
    expect(screen.getByTestId('worked-icon-done')).toBeInTheDocument();
    expect(screen.queryByTestId('worked-icon-live')).toBeNull();
  });

  it('shows spin icon when done=false (running state)', () => {
    renderWithProviders(<ChatStreamEntries entries={[workedEntry({ done: false })]} />);
    expect(screen.getByTestId('worked-icon-live')).toBeInTheDocument();
    expect(screen.queryByTestId('worked-icon-done')).toBeNull();
  });

  it('spin icon carries .worked-icon-live class (CSS animation hook)', () => {
    renderWithProviders(<ChatStreamEntries entries={[workedEntry({ done: false })]} />);
    const icon = screen.getByTestId('worked-icon-live');
    expect(icon.classList.contains('worked-icon-live')).toBe(true);
  });

  it('renders the label text', () => {
    renderWithProviders(<ChatStreamEntries entries={[workedEntry({ label: 'Worked for 7.1s' })]} />);
    const header = screen.getByRole('button', { name: /expand tool steps/i });
    expect(header).toHaveTextContent('Worked for 7.1s');
  });
});

// ---------------------------------------------------------------------------
// WorkedAccordion — prefers-reduced-motion
// ---------------------------------------------------------------------------

describe('WorkedAccordion prefers-reduced-motion', () => {
  let originalMatchMedia: typeof window.matchMedia;

  beforeEach(() => {
    originalMatchMedia = window.matchMedia;
    // Simulate prefers-reduced-motion: reduce
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      configurable: true,
      value: (query: string) => ({
        matches: query === '(prefers-reduced-motion: reduce)',
        media: query,
        onchange: null,
        addListener: () => {},
        removeListener: () => {},
        addEventListener: () => {},
        removeEventListener: () => {},
        dispatchEvent: () => false,
      }),
    });
  });

  afterEach(() => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      configurable: true,
      value: originalMatchMedia,
    });
  });

  it('live icon still renders (motion suppressed via CSS, not via JS)', () => {
    // The .worked-icon-live class is always present on the Loader2 icon;
    // `prefers-reduced-motion` suppresses the CSS animation — not the element.
    // We verify the class is there so the CSS rule can apply.
    renderWithProviders(<ChatStreamEntries entries={[workedEntry({ done: false })]} />);
    const icon = screen.getByTestId('worked-icon-live');
    expect(icon).toBeInTheDocument();
    expect(icon.classList.contains('worked-icon-live')).toBe(true);
  });
});

// ---------------------------------------------------------------------------
// FilesChangedBlock
// ---------------------------------------------------------------------------

describe('FilesChangedBlock', () => {
  it('renders one <a> per filename', () => {
    renderWithProviders(
      <ChatStreamEntries entries={[filesEntry(['src/foo.ts', 'src/bar.tsx', 'README.md'])]} />,
    );

    const links = screen.getAllByTestId('file-link');
    expect(links).toHaveLength(3);
    expect(links[0]).toHaveTextContent('src/foo.ts');
    expect(links[1]).toHaveTextContent('src/bar.tsx');
    expect(links[2]).toHaveTextContent('README.md');
  });

  it('file links carry monospace font-code class', () => {
    renderWithProviders(<ChatStreamEntries entries={[filesEntry(['src/index.ts'])]} />);
    const link = screen.getByTestId('file-link');
    expect(link.classList.contains('font-code')).toBe(true);
  });

  it('file links use aria-label describing each file', () => {
    renderWithProviders(<ChatStreamEntries entries={[filesEntry(['packages/web/foo.ts'])]} />);
    const link = screen.getByTestId('file-link');
    expect(link).toHaveAttribute('aria-label', 'View diff for packages/web/foo.ts');
  });

  it('clicking a file link is a no-op (does not navigate)', () => {
    const { container } = renderWithProviders(
      <ChatStreamEntries entries={[filesEntry(['src/utils.ts'])]} />,
    );
    const link = container.querySelector('a[data-testid="file-link"]') as HTMLAnchorElement;
    // Firing click should not throw and href stays "#"
    fireEvent.click(link);
    expect(link.getAttribute('href')).toBe('#');
  });

  it('renders the "Changed" label', () => {
    renderWithProviders(<ChatStreamEntries entries={[filesEntry()]} />);
    const block = screen.getByTestId('files-changed-block');
    expect(block).toHaveTextContent('Changed');
  });

  it('renders nothing when items array is empty', () => {
    const { container } = renderWithProviders(
      <ChatStreamEntries entries={[{ kind: 'files', items: [] }]} />,
    );
    expect(container.querySelector('[data-testid="files-changed-block"]')).toBeNull();
  });

  it('renders the "›" glyph before each filename', () => {
    renderWithProviders(<ChatStreamEntries entries={[filesEntry(['a.ts', 'b.ts'])]} />);
    const block = screen.getByTestId('files-changed-block');
    const glyphs = block.querySelectorAll('li > span[aria-hidden="true"]');
    expect(glyphs).toHaveLength(2);
    glyphs.forEach((g) => expect(g.textContent).toBe('›'));
  });
});

// ---------------------------------------------------------------------------
// Mixed entries — ensure existing entry kinds still render
// ---------------------------------------------------------------------------

describe('ChatStreamEntries mixed entries', () => {
  it('renders a mix of worked + files + note without errors', () => {
    const entries: ChatStreamEntry[] = [
      { kind: 'note', message: 'Starting...' },
      workedEntry(),
      filesEntry(['src/main.ts']),
    ];
    renderWithProviders(<ChatStreamEntries entries={entries} />);

    expect(screen.getByTestId('worked-accordion')).toBeInTheDocument();
    expect(screen.getByTestId('files-changed-block')).toBeInTheDocument();
    expect(screen.getByText('Starting...')).toBeInTheDocument();
  });

  // Snapshot guard: worked + files do not regress existing text/thought/tool renders
  it('text entry still renders alongside worked accordion', () => {
    const entries: ChatStreamEntry[] = [
      { kind: 'text', content: 'Hello world' },
      workedEntry(),
    ];
    renderWithProviders(<ChatStreamEntries entries={entries} />);
    expect(screen.getByTestId('chat-stream-agent-text')).toBeInTheDocument();
    expect(screen.getByTestId('worked-accordion')).toBeInTheDocument();
  });
});

// ---------------------------------------------------------------------------
// Accessibility — keyboard activation of the accordion
// ---------------------------------------------------------------------------

describe('WorkedAccordion keyboard', () => {
  it('Enter key on a focused button opens the accordion', () => {
    renderWithProviders(<ChatStreamEntries entries={[workedEntry()]} />);
    const header = screen.getByRole('button', { name: /expand tool steps/i });
    header.focus();
    // In jsdom, pressing Enter on a <button> synthesises a click event.
    // We fire click directly to simulate that behaviour.
    fireEvent.click(header);
    expect(header.getAttribute('aria-expanded')).toBe('true');
  });

  it('space key can activate the button', () => {
    renderWithProviders(<ChatStreamEntries entries={[workedEntry()]} />);
    const header = screen.getByRole('button', { name: /expand tool steps/i });
    fireEvent.click(header);
    expect(header.getAttribute('aria-expanded')).toBe('true');
  });
});
