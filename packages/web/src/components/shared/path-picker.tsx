import { useState, useEffect, useCallback } from 'react';
import {
  ChevronRight,
  Folder,
  FolderGit2,
  FolderOpen,
  Home,
  Loader2,
} from 'lucide-react';
import { apiClient } from '@/lib/api/client';
import type { FsEntry } from '@/lib/api/types';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

interface PathPickerProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onSelect: (path: string) => void;
  title?: string;
  description?: string;
  /** If true, only git repos can be selected. Default false. */
  gitOnly?: boolean;
}

export function PathPicker({
  open,
  onOpenChange,
  onSelect,
  title = 'Select folder',
  description = 'Browse the server filesystem to select a directory.',
  gitOnly = false,
}: PathPickerProps) {
  const [currentPath, setCurrentPath] = useState('~');
  const [resolvedPath, setResolvedPath] = useState('');
  const [entries, setEntries] = useState<FsEntry[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [manualPath, setManualPath] = useState('');

  const browse = useCallback(async (path: string) => {
    setLoading(true);
    setError(null);
    try {
      const result = await apiClient.browsePath(path);
      setResolvedPath(result.path);
      setEntries(result.entries);
      setManualPath(result.path);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Failed to browse directory');
      setEntries([]);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (open) {
      browse(currentPath);
    }
  }, [open, currentPath, browse]);

  const navigateTo = (path: string) => {
    setCurrentPath(path);
  };

  const navigateUp = () => {
    const parent = resolvedPath.split('/').slice(0, -1).join('/') || '/';
    navigateTo(parent);
  };

  const handleManualNav = () => {
    const trimmed = manualPath.trim();
    if (trimmed) navigateTo(trimmed);
  };

  const handleSelect = () => {
    onSelect(resolvedPath);
    onOpenChange(false);
  };

  const breadcrumbs = resolvedPath.split('/').filter(Boolean);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="max-h-[80vh] sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>{title}</DialogTitle>
          <DialogDescription>{description}</DialogDescription>
        </DialogHeader>

        {/* Path bar */}
        <div className="flex items-center gap-2">
          <div className="relative min-w-0 flex-1">
            <FolderOpen className="pointer-events-none absolute left-3 top-1/2 size-4 -translate-y-1/2 text-[var(--muted-foreground)]" />
            <Input
              value={manualPath}
              onChange={(e) => setManualPath(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleManualNav()}
              placeholder="/path/to/directory"
              className="h-9 pl-10 pr-4 font-mono text-sm"
            />
          </div>
          <Button variant="outline" size="sm" onClick={handleManualNav}>
            Go
          </Button>
        </div>

        {/* Breadcrumb */}
        <div className="flex flex-wrap items-center gap-1 text-xs text-[var(--muted-foreground)]">
          <button
            type="button"
            onClick={() => navigateTo('/')}
            className="inline-flex items-center gap-1 px-1.5 py-0.5 hover:bg-[var(--muted)] hover:text-[var(--foreground)]"
          >
            <Home className="size-3" />
          </button>
          {breadcrumbs.map((segment, i) => {
            const segmentPath = '/' + breadcrumbs.slice(0, i + 1).join('/');
            return (
              <span key={segmentPath} className="inline-flex items-center gap-1">
                <ChevronRight className="size-3" />
                <button
                  type="button"
                  onClick={() => navigateTo(segmentPath)}
                  className=" px-1.5 py-0.5 hover:bg-[var(--muted)] hover:text-[var(--foreground)]"
                >
                  {segment}
                </button>
              </span>
            );
          })}
        </div>

        {/* Entry list */}
        <div className="max-h-[40vh] min-h-[12rem] overflow-y-auto border border-[color:var(--border-subtle)] bg-[color:var(--surface-1)]">
          {loading ? (
            <div className="flex h-32 items-center justify-center">
              <Loader2 className="size-5 animate-spin text-[var(--muted-foreground)]" />
            </div>
          ) : error ? (
            <div className="p-4 text-sm text-[var(--destructive)]">{error}</div>
          ) : entries.length === 0 ? (
            <div className="flex h-32 items-center justify-center text-sm text-[var(--muted-foreground)]">
              Empty directory
            </div>
          ) : (
            <div className="divide-y divide-[color:var(--border-subtle)]">
              {/* Go up */}
              <button
                type="button"
                onClick={navigateUp}
                className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm transition-colors hover:bg-[color:var(--surface-2)]"
              >
                <Folder className="size-4 text-[var(--muted-foreground)]" />
                <span className="text-[var(--muted-foreground)]">..</span>
              </button>
              {entries.map((entry) => (
                <button
                  type="button"
                  key={entry.path}
                  onClick={() => {
                    if (entry.is_git_repo && gitOnly) {
                      onSelect(entry.path);
                      onOpenChange(false);
                    } else {
                      navigateTo(entry.path);
                    }
                  }}
                  onDoubleClick={() => {
                    if (!gitOnly) {
                      onSelect(entry.path);
                      onOpenChange(false);
                    }
                  }}
                  className={`flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm transition-colors hover:bg-[color:var(--surface-2)] ${
                    entry.is_git_repo
                      ? 'bg-[var(--primary)]/5'
                      : ''
                  }`}
                >
                  {entry.is_git_repo ? (
                    <FolderGit2 className="size-4 text-[var(--primary)]" />
                  ) : (
                    <Folder className="size-4 text-[var(--muted-foreground)]" />
                  )}
                  <span className="min-w-0 flex-1 truncate">{entry.name}</span>
                  {entry.is_git_repo && (
                    <span className="shrink-0 border border-[var(--primary)]/30 bg-[var(--primary)]/10 px-2 py-0.5 text-[10px] font-medium text-[var(--primary)]">
                      git repo
                    </span>
                  )}
                  <ChevronRight className="size-3.5 text-[var(--muted-foreground)]" />
                </button>
              ))}
            </div>
          )}
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleSelect} disabled={!resolvedPath}>
            <FolderOpen className="size-4" />
            Select {resolvedPath.split('/').at(-1) || 'folder'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
