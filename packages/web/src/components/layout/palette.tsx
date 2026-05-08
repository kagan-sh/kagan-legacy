import { useState, useEffect, useRef, useCallback, useMemo } from 'react';
import { useNavigate } from 'react-router';
import { useAtom, useSetAtom } from 'jotai';
import { Search, LayoutGrid, MessageSquareText, Sun, Settings, Plus, Activity } from 'lucide-react';
import { commandPaletteOpenAtom } from '@/lib/atoms/ui';
import { boardDialogAtom } from '@/lib/atoms/board';
import { apiClient } from '@/lib/api/client';
import { cn } from '@/lib/utils';

interface PaletteAction {
  id: string;
  label: string;
  shortcut?: string;
  group: string;
  action: () => void;
}

export function Palette() {
  const [open, setOpen] = useAtom(commandPaletteOpenAtom);
  const navigate = useNavigate();
  const setBoardDialog = useSetAtom(boardDialogAtom);
  const [query, setQuery] = useState('');
  const [selectedIdx, setSelectedIdx] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const actions = useMemo<PaletteAction[]>(() => [
    {
      id: 'create-task',
      label: 'Create task',
      shortcut: 'n',
      group: 'Tasks',
      action: () => { setBoardDialog({ kind: 'create' }); setOpen(false); },
    },
    {
      id: 'new-orch-session',
      label: 'New orchestrator session',
      group: 'Sessions',
      action: () => {
        apiClient.createSession({ type: 'orchestrator', title: 'New conversation' })
          .then((s) => { navigate(`/chat/${s.id}`); setOpen(false); })
          .catch(() => {});
      },
    },
    {
      id: 'new-general-session',
      label: 'New general session',
      group: 'Sessions',
      action: () => {
        apiClient.createSession({ type: 'general', title: 'New conversation' })
          .then((s) => { navigate(`/chat/${s.id}`); setOpen(false); })
          .catch(() => {});
      },
    },
    {
      id: 'switch-board',
      label: 'Switch to Board',
      group: 'Navigation',
      action: () => { navigate('/board'); setOpen(false); },
    },
    {
      id: 'switch-chat',
      label: 'Switch to Chat',
      group: 'Navigation',
      action: () => { navigate('/chat'); setOpen(false); },
    },
    {
      id: 'toggle-theme',
      label: 'Toggle theme',
      shortcut: 'Cmd+Shift+L',
      group: 'Preferences',
      action: () => {
        const isLight = document.documentElement.classList.contains('light');
        if (isLight) {
          document.documentElement.classList.remove('light');
        } else {
          document.documentElement.classList.add('light');
        }
        localStorage.setItem('kagan_theme_mode', isLight ? 'dark' : 'light');
        setOpen(false);
      },
    },
    {
      id: 'settings',
      label: 'Settings',
      group: 'Preferences',
      action: () => { navigate('/settings'); setOpen(false); },
    },
  ], [navigate, setBoardDialog, setOpen]);

  const filtered = useMemo(() => {
    if (!query.trim()) return actions;
    const q = query.toLowerCase();
    return actions.filter((a) => a.label.toLowerCase().includes(q) || a.group.toLowerCase().includes(q));
  }, [query, actions]);

  // Reset on open/close
  useEffect(() => {
    if (open) {
      setQuery('');
      setSelectedIdx(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  // Reset selected index when filtered list changes
  useEffect(() => {
    setSelectedIdx(0);
  }, [filtered.length]);

  const onKeyDown = useCallback((e: React.KeyboardEvent) => {
    if (e.key === 'ArrowDown') {
      e.preventDefault();
      setSelectedIdx((prev) => Math.min(prev + 1, filtered.length - 1));
    } else if (e.key === 'ArrowUp') {
      e.preventDefault();
      setSelectedIdx((prev) => Math.max(prev - 1, 0));
    } else if (e.key === 'Enter') {
      e.preventDefault();
      const selected = filtered[selectedIdx];
      if (selected) selected.action();
    } else if (e.key === 'Escape') {
      e.preventDefault();
      setOpen(false);
    }
  }, [filtered, selectedIdx, setOpen]);

  if (!open) return null;

  return (
    <div className="fixed inset-0 z-[100] flex items-start justify-center pt-[20vh]">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-[var(--surface-overlay)]"
        onClick={() => setOpen(false)}
      />
      {/* Panel */}
      <div
        className="relative z-10 w-full max-w-lg overflow-hidden border border-[color:var(--border)] bg-[color:var(--surface-1)] shadow-2xl"
        style={{ borderRadius: '6px' }}
      >
        <div className="flex items-center gap-2 border-b border-[color:var(--border-subtle)] px-4 py-3">
          <Search className="size-4 shrink-0 text-[var(--muted-foreground)]" />
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            onKeyDown={onKeyDown}
            placeholder="Type a command..."
            className="flex-1 border-none bg-transparent text-sm text-[var(--foreground)] outline-none placeholder:text-[var(--muted-foreground)]"
          />
          <kbd className="px-1.5 py-0.5 font-code text-[10px] text-[var(--muted-foreground)] border border-[color:var(--border-subtle)]" style={{ borderRadius: '4px' }}>
            esc
          </kbd>
        </div>

        <div className="max-h-[320px] overflow-y-auto p-2">
          {filtered.length === 0 ? (
            <div className="px-3 py-8 text-center text-sm text-[var(--muted-foreground)]">
              No matching commands
            </div>
          ) : (
            <>
              {Array.from(new Set(filtered.map((a) => a.group))).map((group) => (
                <div key={group} className="mb-1">
                  <div className="px-3 pt-2 pb-1 text-[11px] font-medium uppercase tracking-wider text-[var(--muted-foreground)]">
                    {group}
                  </div>
                  {filtered
                    .filter((a) => a.group === group)
                    .map((action) => {
                      const globalIdx = filtered.indexOf(action);
                      return (
                        <button
                          type="button"
                          key={action.id}
                          onClick={() => action.action()}
                          onMouseEnter={() => setSelectedIdx(globalIdx)}
                          className={cn(
                            'flex w-full items-center gap-3 px-3 py-2 text-left text-sm transition-colors',
                            'hover:bg-[color:var(--accent)]',
                            selectedIdx === globalIdx && 'bg-[color:var(--accent)] text-[var(--foreground)]',
                          )}
                          style={{ borderRadius: '4px' }}
                        >
                          <span className="text-[var(--muted-foreground)]">
                            {action.id.startsWith('create') || action.id.startsWith('new') ? (
                              <Plus className="size-3.5" />
                            ) : action.id === 'switch-board' ? (
                              <LayoutGrid className="size-3.5" />
                            ) : action.id === 'switch-chat' ? (
                              <MessageSquareText className="size-3.5" />
                            ) : action.id === 'toggle-theme' ? (
                              <Sun className="size-3.5" />
                            ) : action.id === 'settings' ? (
                              <Settings className="size-3.5" />
                            ) : (
                              <Activity className="size-3.5" />
                            )}
                          </span>
                          <span className="flex-1 text-[var(--foreground)]">{action.label}</span>
                          {action.shortcut && (
                            <kbd className="px-1.5 py-0.5 font-code text-[10px] text-[var(--muted-foreground)] border border-[color:var(--border-subtle)]" style={{ borderRadius: '4px' }}>
                              {action.shortcut}
                            </kbd>
                          )}
                        </button>
                      );
                    })}
                </div>
              ))}
            </>
          )}
        </div>
      </div>
    </div>
  );
}
