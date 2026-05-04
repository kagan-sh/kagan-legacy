import { useState, useEffect, useCallback } from 'react';
import {
  ChevronRight,
  Folder,
  FolderGit2,
  FolderOpen,
  Home,
  Link2,
  Loader2,
} from 'lucide-react';
import { apiClient } from '@/lib/api/client';
import type { FsEntry } from '@kagan/shared-api-client';
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

/**
 * Build breadcrumb segments from a resolved path and server-provided context.
 *
 * Returns an array of { label, target } pairs where:
 * - label  — the display name of the segment
 * - target — the absolute path to navigate to when the crumb is clicked
 *
 * Examples:
 *   POSIX /Users/you/dev  → [{ label:'Users', target:'/Users' }, { label:'you', target:'/Users/you' }, ...]
 *   Windows C:\Users\you  → [{ label:'C:', target:'C:\\' }, { label:'Users', target:'C:\\Users' }, ...]
 */
function buildBreadcrumbs(
  resolvedPath: string,
  separator: string,
  roots: string[],
): { label: string; target: string }[] {
  const segments = resolvedPath.split(separator).filter(Boolean);
  if (segments.length === 0) return [];

  // Determine if this is a Windows-style path by checking whether the first
  // segment matches any known root (e.g. "C:" matches root "C:\").
  const firstSegment = segments[0] ?? '';
  const firstMatchedRoot = roots.find(
    (r) => r.toUpperCase() === firstSegment.toUpperCase() + separator,
  );
  const isWindowsStyle = firstMatchedRoot !== undefined;

  return segments.map((segment, i) => {
    let target: string;

    if (isWindowsStyle) {
      if (i === 0) {
        // Drive root: navigate to "C:\" not "C:" (bare drive = cwd on that drive).
        target = firstMatchedRoot!;
      } else {
        target = firstMatchedRoot! + segments.slice(1, i + 1).join(separator);
      }
    } else {
      // POSIX: paths are rooted with a leading separator.
      target = separator + segments.slice(0, i + 1).join(separator);
    }

    return { label: segment, target };
  });
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
  const [parent, setParent] = useState<string | null>(null);
  const [separator, setSeparator] = useState('/');
  const [roots, setRoots] = useState<string[]>(['/']);
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
      setParent(result.parent);
      setSeparator(result.separator);
      setRoots(result.roots);
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
    if (parent !== null) {
      navigateTo(parent);
    }
  };

  const handleManualNav = () => {
    const trimmed = manualPath.trim();
    if (trimmed) navigateTo(trimmed);
  };

  const handleSelect = () => {
    onSelect(resolvedPath);
    onOpenChange(false);
  };

  const breadcrumbs = buildBreadcrumbs(resolvedPath, separator, roots);

  // Last segment for the Select button label
  const lastSegment =
    resolvedPath.split(separator).filter(Boolean).at(-1) ?? 'folder';

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
              placeholder="Enter a path or browse"
              className="h-9 pl-10 pr-4 font-mono text-sm"
            />
          </div>
          <Button variant="outline" size="sm" onClick={handleManualNav}>
            Go
          </Button>
        </div>

        {/* Breadcrumb + home + root pickers */}
        <div className="flex flex-wrap items-center gap-1 text-xs text-[var(--muted-foreground)]">
          {/* Home button — always navigates to "~" so the server expands correctly */}
          <button
            type="button"
            onClick={() => navigateTo('~')}
            className="inline-flex items-center gap-1 px-1.5 py-0.5 hover:bg-[var(--muted)] hover:text-[var(--foreground)]"
            aria-label="Home"
          >
            <Home className="size-3" />
          </button>

          {/* Drive/root pickers — only shown when the server reports multiple roots (Windows) */}
          {roots.length > 1 &&
            roots.map((root) => {
              // Display "C:" not "C:\" for brevity
              const label = root.endsWith(separator)
                ? root.slice(0, -separator.length)
                : root;
              return (
                <button
                  key={root}
                  type="button"
                  onClick={() => navigateTo(root)}
                  className="inline-flex items-center gap-0.5 px-1.5 py-0.5 font-mono hover:bg-[var(--muted)] hover:text-[var(--foreground)]"
                  aria-label={`Browse ${root}`}
                >
                  {label}
                </button>
              );
            })}

          {/* Breadcrumb segments built from server-provided separator */}
          {breadcrumbs.map(({ label, target }) => (
            <span key={target} className="inline-flex items-center gap-1">
              <ChevronRight className="size-3" />
              <button
                type="button"
                onClick={() => navigateTo(target)}
                className="px-1.5 py-0.5 hover:bg-[var(--muted)] hover:text-[var(--foreground)]"
              >
                {label}
              </button>
            </span>
          ))}
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
              {/* Go up — disabled (hidden) when at a filesystem root */}
              {parent !== null && (
                <button
                  type="button"
                  onClick={navigateUp}
                  className="flex w-full items-center gap-3 px-4 py-2.5 text-left text-sm transition-colors hover:bg-[color:var(--surface-2)]"
                >
                  <Folder className="size-4 text-[var(--muted-foreground)]" />
                  <span className="text-[var(--muted-foreground)]">..</span>
                </button>
              )}
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
                    entry.is_git_repo ? 'bg-[var(--primary)]/5' : ''
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
                  {entry.is_link && (
                    <span className="inline-flex shrink-0 items-center gap-0.5 border border-[var(--muted-foreground)]/30 bg-[var(--muted)]/40 px-2 py-0.5 text-[10px] font-medium text-[var(--muted-foreground)]">
                      <Link2 className="size-2.5" />
                      link
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
            Select {lastSegment}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
