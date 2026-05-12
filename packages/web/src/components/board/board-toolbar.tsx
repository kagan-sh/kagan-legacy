import type { RefObject } from 'react';
import { Folder, Filter, Plus } from 'lucide-react';
import type { BoardViewMode } from '@/lib/atoms/shell';
import type { WireProject } from '@kagan/shared-api-client';

interface BoardToolbarProps {
  project: WireProject | null;
  totalTasks: number;
  view: BoardViewMode;
  setView: (view: BoardViewMode) => void;
  onCreateTask: () => void;
  onFilterClick?: () => void;
  searchInputRef?: RefObject<HTMLInputElement | null>;
}

export function BoardToolbar({
  project,
  totalTasks,
  view,
  setView,
  onCreateTask,
  onFilterClick,
}: BoardToolbarProps) {
  const projectName = project?.name ?? 'Workspace';

  return (
    <header
      className="flex items-center gap-4 border-b px-6"
      style={{
        height: '50px',
        borderColor: 'var(--border)',
        background: 'var(--surface-0)',
        flexShrink: 0,
      }}
    >
      {/* Breadcrumb */}
      <div
        className="flex items-center gap-2"
        style={{ fontFamily: 'var(--font-code)', fontSize: '12px', color: 'var(--fg-muted)' }}
        aria-label="Board location"
      >
        <Folder
          style={{ width: 14, height: 14, color: 'var(--fg-dim)' }}
          aria-hidden="true"
        />
        <b style={{ color: 'var(--fg)', fontWeight: 500 }} data-testid="crumb-project">
          {projectName}
        </b>
        <span style={{ color: 'var(--fg-dim)' }} aria-hidden="true">/</span>
        <span>main</span>
        <span style={{ color: 'var(--fg-dim)' }} aria-hidden="true">·</span>
        <span data-testid="crumb-total">{totalTasks} tasks</span>
      </div>

      {/* Right controls */}
      <div className="ml-auto flex items-center gap-2">
        {/* Filter chip */}
        <button
          type="button"
          onClick={onFilterClick}
          aria-label="Open filter"
          className="inline-flex items-center gap-1.5"
          style={{
            padding: '4px 10px',
            background: 'var(--surface-1)',
            border: '1px solid var(--border)',
            borderRadius: 6,
            fontSize: 12,
            color: 'var(--fg-muted)',
            cursor: 'pointer',
            fontFamily: 'inherit',
          }}
        >
          <Filter style={{ width: 12, height: 12 }} aria-hidden="true" />
          <span>Filter</span>
        </button>

        {/* Board / List segmented control */}
        <div
          role="group"
          aria-label="Board view mode"
          className="inline-flex overflow-hidden"
          style={{
            background: 'var(--surface-1)',
            border: '1px solid var(--border)',
            borderRadius: 6,
          }}
        >
          {(['board', 'list'] as const).map((mode) => {
            const isActive = view === mode;
            return (
              <button
                key={mode}
                type="button"
                aria-label={mode === 'board' ? 'Board view' : 'List view'}
                aria-current={isActive ? true : undefined}
                data-active={isActive ? 'true' : 'false'}
                data-testid={`view-mode-${mode}`}
                onClick={() => setView(mode)}
                style={{
                  padding: '4px 10px',
                  background: isActive ? 'var(--surface-3)' : 'transparent',
                  color: isActive ? 'var(--fg)' : 'var(--fg-muted)',
                  border: 0,
                  fontFamily: 'var(--font-code)',
                  fontSize: 10.5,
                  letterSpacing: '0.18em',
                  textTransform: 'uppercase',
                  cursor: 'pointer',
                }}
              >
                {mode === 'board' ? 'Board' : 'List'}
              </button>
            );
          })}
        </div>

        {/* New task CTA */}
        <button
          type="button"
          onClick={onCreateTask}
          aria-label="Create new task"
          className="inline-flex items-center gap-1.5 cta-glow"
          style={{
            padding: '5px 12px',
            background: 'var(--primary)',
            color: '#0b0a09',
            border: 0,
            borderRadius: 6,
            fontFamily: 'var(--font-ui)',
            fontSize: 12,
            fontWeight: 600,
            cursor: 'pointer',
            boxShadow: '0 0 18px -4px rgba(212,168,75,0.5)',
          }}
        >
          <Plus style={{ width: 13, height: 13, strokeWidth: 2.5 }} aria-hidden="true" />
          New task
        </button>
      </div>
    </header>
  );
}

interface KbHintFooterProps {
  runningCount: number;
}

export function KbHintFooter({ runningCount }: KbHintFooterProps) {
  return (
    <footer
      className="flex flex-wrap items-center gap-4"
      style={{
        borderTop: '1px solid var(--border)',
        background: 'var(--surface-0)',
        padding: '8px 18px',
        fontFamily: 'var(--font-code)',
        fontSize: 10.5,
        color: 'var(--fg-muted)',
        flexShrink: 0,
      }}
      aria-label="Keyboard shortcuts"
    >
      <HintChunk keys={['j', 'k']} label="nav" />
      <HintChunk keys={['h', 'l']} label="column" />
      <HintChunk keys={['↵']} label="open task" />
      <HintChunk keys={['n']} label="new" />
      <HintChunk keys={['/']} label="filter" />
      <span>
        <Kbd>⌘1</Kbd>
        {' ↔ '}
        <Kbd>⌘2</Kbd>
        {' switch view'}
      </span>

      <span
        className="ml-auto"
        style={{ color: 'var(--primary)' }}
        data-testid="hint-running"
        aria-label={`${runningCount} running, daemon connected`}
      >
        {runningCount} running · daemon connected
      </span>
    </footer>
  );
}

function HintChunk({ keys, label }: { keys: string[]; label: string }) {
  return (
    <span>
      {keys.map((k, i) => (
        <span key={k}>
          {i > 0 && '/'}
          <Kbd>{k}</Kbd>
        </span>
      ))}
      {' '}
      {label}
    </span>
  );
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd
      style={{
        background: 'var(--surface-2)',
        border: '1px solid var(--border)',
        color: 'var(--primary)',
        padding: '1px 6px',
        borderRadius: 3,
        fontSize: 10,
        marginRight: 4,
        fontFamily: 'var(--font-code)',
      }}
    >
      {children}
    </kbd>
  );
}
