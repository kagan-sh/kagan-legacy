import { lazy, Suspense, useEffect, useMemo, useState } from 'react';
import { useAtomValue } from 'jotai';
import { resolvedThemeAtom } from '@/lib/atoms/theme';
import { AlignJustify, Columns2, ChevronDown, ChevronRight, FileCode, FileEdit, FileMinus, FilePlus, Maximize2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { apiClient, ApiError } from '@/lib/api/client';
import { Empty, EmptyHeader, EmptyMedia, EmptyTitle, EmptyDescription } from '@/components/ui/empty';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import { Dialog, DialogContent, DialogHeader, DialogTitle, DialogDescription } from '@/components/ui/dialog';
import { loadDiffViewMode, saveDiffViewMode, type DiffViewModePreference } from '@/lib/utils/storage';
import { parseUnifiedDiff, languageFromPath } from '@/lib/utils/diff';
import type { DiffStats, DiffFile } from '@/lib/api/types';

interface DiffViewerProps {
  taskId: string;
  taskStatus?: string;
  className?: string;
}

const FILE_STATUS_ICON: Record<string, typeof FileCode> = {
  added: FilePlus,
  modified: FileEdit,
  deleted: FileMinus,
};

const LazyDiffEditor = lazy(() =>
  import('@monaco-editor/react').then(module => ({ default: module.DiffEditor }))
);

const LazyEditor = lazy(() =>
  import('@monaco-editor/react').then(module => ({ default: module.Editor }))
);

const EditorLoadingFallback = () => (
  <div className="h-[28rem] w-full bg-[var(--muted)] animate-pulse flex items-center justify-center">
    <span className="text-sm text-[var(--muted-foreground)]">Loading editor...</span>
  </div>
);

const EditorLoadingFallbackFullscreen = () => (
  <div className="w-full h-full bg-[var(--muted)] animate-pulse flex items-center justify-center">
    <span className="text-sm text-[var(--muted-foreground)]">Loading editor...</span>
  </div>
);

type DiffViewMode = DiffViewModePreference;

export function DiffViewer({ taskId, taskStatus, className }: DiffViewerProps) {
  const [stats, setStats] = useState<DiffStats | null>(null);
  const [files, setFiles] = useState<DiffFile[]>([]);
  const [diffText, setDiffText] = useState('');
  const [expanded, setExpanded] = useState(true);
  const [loading, setLoading] = useState(true);
  const [noWorkspace, setNoWorkspace] = useState(false);
  const [selectedPath, setSelectedPath] = useState<string | null>(null);
  const [viewMode, setViewMode] = useState<DiffViewMode>('split');
  const [fullscreen, setFullscreen] = useState(false);

  const parsedFiles = useMemo(() => parseUnifiedDiff(diffText), [diffText]);

  const fileStatsByPath = useMemo(
    () => new Map(files.map((file) => [file.path, file])),
    [files],
  );

  const displayFiles = useMemo(() => {
    if (parsedFiles.length > 0) {
      return parsedFiles.map((file) => file.path);
    }
    return files.map((file) => file.path);
  }, [parsedFiles, files]);

  const selectedParsedFile = useMemo(() => {
    if (!selectedPath) {
      return null;
    }
    return parsedFiles.find((file) => file.path === selectedPath) ?? null;
  }, [parsedFiles, selectedPath]);

  const resolvedTheme = useAtomValue(resolvedThemeAtom);
  const monacoTheme = resolvedTheme === 'dark' ? 'vs-dark' : 'vs';

  useEffect(() => {
    const savedMode = loadDiffViewMode();
    if (savedMode) {
      setViewMode(savedMode);
    }
  }, []);

  useEffect(() => {
    saveDiffViewMode(viewMode);
  }, [viewMode]);

  useEffect(() => {
    let cancelled = false;
    (async () => {
      setLoading(true);
      setNoWorkspace(false);
      setDiffText('');
      setSelectedPath(null);
      if (taskStatus === 'BACKLOG') {
        if (!cancelled) {
          setNoWorkspace(true);
          setLoading(false);
        }
        return;
      }
      try {
        const worktree = await apiClient.getTaskWorktree(taskId);
        if (!worktree.worktree) {
          if (!cancelled) {
            setNoWorkspace(true);
            setStats(null);
            setFiles([]);
          }
          return;
        }
        const [s, f, raw] = await Promise.all([
          apiClient.getDiffStats(taskId),
          apiClient.getDiffFiles(taskId),
          apiClient.getDiffRaw(taskId),
        ]);
        if (!cancelled) {
          setStats(s);
          setFiles(f);
          setDiffText(raw);

          const parsed = parseUnifiedDiff(raw);
          const defaultPath = parsed[0]?.path ?? f[0]?.path ?? null;
          setSelectedPath(defaultPath);
        }
      } catch (error) {
        if (!cancelled) {
          if (error instanceof ApiError && (error.status === 404 || error.detail?.includes('workspace'))) {
            setNoWorkspace(true);
            setStats(null);
            setFiles([]);
            setDiffText('');
            setSelectedPath(null);
          }
        }
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => { cancelled = true; };
  }, [taskId, taskStatus]);

  if (loading) {
    return (
      <div className={className}>
        <div className="h-16 animate-pulse bg-[var(--muted)]" />
      </div>
    );
  }

  if (noWorkspace || !stats || stats.files_changed === 0) {
    return (
      <div className={className}>
        <Empty>
          <EmptyHeader>
            <EmptyMedia variant="icon"><FileCode className="size-8" /></EmptyMedia>
            <EmptyTitle>No code changes yet</EmptyTitle>
            <EmptyDescription>Start the agent to see diffs here.</EmptyDescription>
          </EmptyHeader>
        </Empty>
      </div>
    );
  }

  return (
    <div className={className}>
      <Button
        variant="ghost"
        className="h-auto w-full justify-start p-0 text-sm font-normal hover:bg-transparent"
        onClick={() => setExpanded(!expanded)}
      >
        {expanded ? (
          <ChevronDown className="size-4" />
        ) : (
          <ChevronRight className="size-4" />
        )}
        <span className="font-medium text-[var(--foreground)]">
          {stats.files_changed} file{stats.files_changed !== 1 ? 's' : ''} changed
        </span>
        <span className="text-[var(--kagan-success)]">+{stats.insertions}</span>
        <span className="text-[var(--destructive)]">-{stats.deletions}</span>
      </Button>

      {expanded && (
        <div className="mt-2 flex items-center justify-end gap-2">
          <span className="text-[10px] text-[var(--muted-foreground)]">View</span>
          <ToggleGroup
            type="single"
            value={viewMode}
            onValueChange={(value) => {
              if (value === 'split' || value === 'unified') {
                setViewMode(value);
              }
            }}
            variant="outline"
            size="sm"
            aria-label="Diff view mode"
          >
            <ToggleGroupItem value="split" aria-label="Split view" title="Split view">
              <Columns2 className="size-3.5" />
              Split
            </ToggleGroupItem>
            <ToggleGroupItem value="unified" aria-label="Unified view" title="Unified view">
              <AlignJustify className="size-3.5" />
              Unified
            </ToggleGroupItem>
          </ToggleGroup>
          <Button
            variant="ghost"
            size="icon-sm"
            onClick={() => setFullscreen(true)}
            aria-label="Fullscreen diff"
            title="Fullscreen"
          >
            <Maximize2 className="size-3.5" />
          </Button>
        </div>
      )}

      {expanded && files.length > 0 && (
        <div className="mt-3 grid gap-3 lg:grid-cols-[17rem_minmax(0,1fr)]">
          <ul className="max-h-[28rem] space-y-1 overflow-y-auto border border-[color:var(--border-subtle)] bg-[var(--card)] p-2 shadow-[var(--soft-shadow)]">
            {displayFiles.map((path) => {
              const file = fileStatsByPath.get(path);
              const Icon = FILE_STATUS_ICON[file?.status ?? 'modified'] ?? FileCode;
              const isSelected = path === selectedPath;

              return (
                <li key={path}>
                  <button
                    type="button"
                    onClick={() => setSelectedPath(path)}
                    className={`flex w-full items-center gap-2 px-2 py-1 text-left text-xs transition-colors ${
 isSelected
 ? 'bg-[var(--sidebar-accent)] text-[var(--sidebar-accent-foreground)]'
 : 'text-[var(--foreground)] hover:bg-[var(--muted)]'
 }`}
                  >
                    <Icon className="size-3 text-[var(--muted-foreground)]" />
                    <span className="flex-1 truncate">{path}</span>
                    <span className="text-[var(--kagan-success)]">+{file?.insertions ?? 0}</span>
                    <span className="text-[var(--destructive)]">-{file?.deletions ?? 0}</span>
                  </button>
                </li>
              );
            })}
          </ul>

          <div className="overflow-hidden border border-[color:var(--border-subtle)] shadow-[var(--soft-shadow)]">
            <Suspense fallback={<EditorLoadingFallback />}>
              {selectedParsedFile ? (
                <LazyDiffEditor
                  height="28rem"
                  language={languageFromPath(selectedParsedFile.path)}
                  original={selectedParsedFile.original}
                  modified={selectedParsedFile.modified}
                  theme={monacoTheme}
                  options={{
                    readOnly: true,
                    renderSideBySide: viewMode === 'split',
                    minimap: { enabled: false },
                    lineNumbersMinChars: 3,
                    scrollBeyondLastLine: false,
                    wordWrap: 'off',
                  }}
                />
              ) : (
                <LazyEditor
                  height="28rem"
                  language="diff"
                  value={diffText}
                  theme={monacoTheme}
                  options={{
                    readOnly: true,
                    minimap: { enabled: false },
                    lineNumbers: 'on',
                    scrollBeyondLastLine: false,
                    wordWrap: 'off',
                  }}
                />
              )}
            </Suspense>
          </div>
        </div>
      )}

      {expanded && files.length === 0 && diffText && (
        <div className="mt-3 overflow-hidden border border-[color:var(--border-subtle)] shadow-[var(--soft-shadow)]">
          <Suspense fallback={<EditorLoadingFallback />}>
            <LazyEditor
              height="28rem"
              language="diff"
              value={diffText}
              theme={monacoTheme}
              options={{
                readOnly: true,
                minimap: { enabled: false },
                lineNumbers: 'on',
                scrollBeyondLastLine: false,
                wordWrap: 'off',
              }}
            />
          </Suspense>
        </div>
      )}

      <Dialog open={fullscreen} onOpenChange={setFullscreen}>
        <DialogContent className="flex inset-0 h-screen w-screen max-w-none sm:max-w-none translate-x-0 translate-y-0 top-0 left-0 rounded-none flex-col gap-0 p-0">
          <DialogHeader className="flex flex-row items-center justify-between gap-3 border-b border-[color:var(--border-subtle)] px-5 py-3">
            <div className="flex items-center gap-3">
              <DialogTitle className="text-sm font-semibold">
                {stats?.files_changed ?? 0} file{(stats?.files_changed ?? 0) !== 1 ? 's' : ''} changed
              </DialogTitle>
              <span className="text-xs text-[var(--kagan-success)]">+{stats?.insertions ?? 0}</span>
              <span className="text-xs text-[var(--destructive)]">-{stats?.deletions ?? 0}</span>
            </div>
            <ToggleGroup
              type="single"
              value={viewMode}
              onValueChange={(value) => {
                if (value === 'split' || value === 'unified') setViewMode(value);
              }}
              variant="outline"
              size="sm"
            >
              <ToggleGroupItem value="split"><Columns2 className="size-3.5" /> Split</ToggleGroupItem>
              <ToggleGroupItem value="unified"><AlignJustify className="size-3.5" /> Unified</ToggleGroupItem>
            </ToggleGroup>
          </DialogHeader>
          <DialogDescription className="sr-only">Full-screen diff viewer for task workspace changes</DialogDescription>
          <div className="grid min-h-0 flex-1 gap-0 lg:grid-cols-[17rem_minmax(0,1fr)]">
            <ul className="min-h-0 space-y-1 overflow-y-auto border-r border-[color:var(--border-subtle)] bg-[var(--card)] p-2">
              {displayFiles.map((path) => {
                const file = fileStatsByPath.get(path);
                const Icon = FILE_STATUS_ICON[file?.status ?? 'modified'] ?? FileCode;
                const isSelected = path === selectedPath;
                return (
                  <li key={path}>
                    <button
                      type="button"
                      onClick={() => setSelectedPath(path)}
                      className={`flex w-full items-center gap-2 px-2 py-1 text-left text-xs transition-colors ${
                        isSelected
                          ? 'bg-[var(--sidebar-accent)] text-[var(--sidebar-accent-foreground)]'
                          : 'text-[var(--foreground)] hover:bg-[var(--muted)]'
                      }`}
                    >
                      <Icon className="size-3 text-[var(--muted-foreground)]" />
                      <span className="flex-1 truncate">{path}</span>
                      <span className="text-[var(--kagan-success)]">+{file?.insertions ?? 0}</span>
                      <span className="text-[var(--destructive)]">-{file?.deletions ?? 0}</span>
                    </button>
                  </li>
                );
              })}
            </ul>
            <div className="min-h-0 overflow-hidden">
              <Suspense fallback={<EditorLoadingFallbackFullscreen />}>
                {selectedParsedFile ? (
                  <LazyDiffEditor
                    height="100%"
                    language={languageFromPath(selectedParsedFile.path)}
                    original={selectedParsedFile.original}
                    modified={selectedParsedFile.modified}
                    theme={monacoTheme}
                    options={{
                      readOnly: true,
                      renderSideBySide: viewMode === 'split',
                      minimap: { enabled: false },
                      lineNumbersMinChars: 3,
                      scrollBeyondLastLine: false,
                      wordWrap: 'off',
                    }}
                  />
                ) : diffText ? (
                  <LazyEditor
                    height="100%"
                    language="diff"
                    value={diffText}
                    theme={monacoTheme}
                    options={{
                      readOnly: true,
                      minimap: { enabled: false },
                      lineNumbers: 'on',
                      scrollBeyondLastLine: false,
                      wordWrap: 'off',
                    }}
                  />
                ) : null}
              </Suspense>
            </div>
          </div>
        </DialogContent>
      </Dialog>
    </div>
  );
}
