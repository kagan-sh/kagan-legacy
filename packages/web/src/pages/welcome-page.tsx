import { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router';
import { useAtomValue, useSetAtom } from 'jotai';
import {
  FolderGit2,
  FolderOpen,
  GitBranch,
  Plus,
  RefreshCw,
  Trash2,
} from 'lucide-react';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api/client';
import type { WireProject, WireRepository } from '@/lib/api/types';
import { isAuthenticatedAtom, retryHealthCheckAtom } from '@/lib/atoms/auth';
import { projectSwitchVersionAtom } from '@/lib/atoms/board';
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
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { PathPicker } from '@/components/shared/path-picker';

interface ProjectWithRepos {
  project: WireProject;
  repos: WireRepository[];
}

export function Component() {
  const navigate = useNavigate();
  const isAuthenticated = useAtomValue(isAuthenticatedAtom);
  const retryHealthCheck = useSetAtom(retryHealthCheckAtom);
  const bumpProjectVersion = useSetAtom(projectSwitchVersionAtom);
  const [retrying, setRetrying] = useState(false);
  const [projects, setProjects] = useState<ProjectWithRepos[]>([]);
  const [loading, setLoading] = useState(true);

  // Expanded project for multi-repo selection
  const [expandedProjectId, setExpandedProjectId] = useState<string | null>(null);

  // New project dialog
  const [createOpen, setCreateOpen] = useState(false);
  const [newName, setNewName] = useState('');
  const [newRepoPath, setNewRepoPath] = useState('');
  const [creating, setCreating] = useState(false);
  const [repoPickerOpen, setRepoPickerOpen] = useState(false);

  // Open folder flow
  const [folderPickerOpen, setFolderPickerOpen] = useState(false);

  // Delete confirmation
  const [deleteTarget, setDeleteTarget] = useState<ProjectWithRepos | null>(null);

  const loadProjects = useCallback(async () => {
    try {
      const data = await apiClient.getProjects();
      const withRepos = await Promise.all(
        data.map(async (project) => {
          try {
            const repos = await apiClient.getProjectRepos(project.id);
            return { project, repos };
          } catch {
            return { project, repos: [] };
          }
        }),
      );
      setProjects(withRepos);
    } catch {
      toast.error('Failed to load projects');
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    loadProjects();
  }, [loadProjects]);

  const activateAndNavigate = useCallback(
    async (projectId: string) => {
      try {
        await apiClient.activateProject(projectId);
        bumpProjectVersion((v) => v + 1);
        navigate('/board');
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'Failed to open project');
      }
    },
    [bumpProjectVersion, navigate],
  );

  const handleOpenProject = useCallback(
    (entry: ProjectWithRepos) => {
      if (entry.repos.length > 1) {
        // Toggle expansion for multi-repo projects
        setExpandedProjectId((prev) => (prev === entry.project.id ? null : entry.project.id));
      } else {
        // Single (or zero) repo: activate and navigate immediately
        setExpandedProjectId(null);
        activateAndNavigate(entry.project.id);
      }
    },
    [activateAndNavigate],
  );

  const handleSelectRepo = useCallback(
    async (project: WireProject, repo: WireRepository) => {
      try {
        await apiClient.activateProject(project.id);
        await apiClient.selectProjectRepo(project.id, repo.id);
        bumpProjectVersion((v) => v + 1);
        navigate('/board');
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'Failed to open project');
      }
    },
    [bumpProjectVersion, navigate],
  );

  // Keyboard shortcuts: 1-9 quick-open, n = new, o = open folder
  useEffect(() => {
    const onKeyDown = (e: KeyboardEvent) => {
      const el = e.target as HTMLElement;
      if (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA' || el.isContentEditable) return;
      if (createOpen || folderPickerOpen || repoPickerOpen || deleteTarget) return;

      if (e.key === 'n') {
        e.preventDefault();
        setCreateOpen(true);
        return;
      }
      if (e.key === 'o') {
        e.preventDefault();
        setFolderPickerOpen(true);
        return;
      }
      const num = parseInt(e.key, 10);
      if (num >= 1 && num <= 9 && num <= projects.length) {
        e.preventDefault();
        const entry = projects[num - 1];
        if (entry) handleOpenProject(entry);
      }
    };
    window.addEventListener('keydown', onKeyDown);
    return () => window.removeEventListener('keydown', onKeyDown);
  }, [projects, createOpen, folderPickerOpen, repoPickerOpen, deleteTarget, handleOpenProject]);

  const handleCreate = useCallback(async () => {
    const name = newName.trim();
    if (!name || creating) return;
    setCreating(true);
    try {
      const created = await apiClient.createProject(name);
      if (newRepoPath.trim()) {
        const repo = await apiClient.addProjectRepo(created.id, newRepoPath.trim());
        await apiClient.selectProjectRepo(created.id, repo.id);
      }
      await apiClient.activateProject(created.id);
      bumpProjectVersion((v) => v + 1);
      setCreateOpen(false);
      setNewName('');
      setNewRepoPath('');
      toast.success(`Created ${created.name}`);
      navigate('/board');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to create project');
    } finally {
      setCreating(false);
    }
  }, [newName, newRepoPath, creating, bumpProjectVersion, navigate]);

  const handleOpenFolder = useCallback(
    async (folderPath: string) => {
      // Check if a project already owns this path
      for (const { project, repos } of projects) {
        if (repos.some((r) => r.path === folderPath)) {
          await activateAndNavigate(project.id);
          return;
        }
      }
      // Infer project name from folder
      const folderName = folderPath.split('/').filter(Boolean).at(-1) ?? 'New project';
      try {
        const created = await apiClient.createProject(folderName);
        const repo = await apiClient.addProjectRepo(created.id, folderPath);
        await apiClient.selectProjectRepo(created.id, repo.id);
        await apiClient.activateProject(created.id);
        bumpProjectVersion((v) => v + 1);
        toast.success(`Created ${created.name}`);
        navigate('/board');
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'Failed to open folder');
      }
    },
    [projects, activateAndNavigate, bumpProjectVersion, navigate],
  );

  const handleDelete = useCallback(async () => {
    if (!deleteTarget) return;
    try {
      await apiClient.deleteProject(deleteTarget.project.id);
      setDeleteTarget(null);
      toast.success('Project deleted');
      loadProjects();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to delete project');
    }
  }, [deleteTarget, loadProjects]);

  if (!isAuthenticated) {
    return (
      <div className="flex min-h-screen flex-col items-center justify-center bg-[color:var(--surface-0)] px-4">
        <div className="w-full max-w-sm text-center">
          <span className="mb-4 inline-flex items-center gap-1.5 bg-[color:var(--surface-1)] px-3 py-1.5 shadow-[var(--ambient-shadow)]">
            <span className="font-code text-sm tracking-[0.08em]">ᘚᘛ</span>
            <span className="font-code text-xs font-semibold uppercase tracking-[0.22em]">Kagan</span>
          </span>
          <h1 className="mt-4 text-sm font-semibold">Connecting to Kagan server...</h1>
          <p className="mt-1.5 text-xs text-[var(--muted-foreground)]">
            Could not connect to Kagan server. Make sure <code className=" bg-[color:var(--surface-2)] px-1.5 py-0.5 font-code text-[10px]">kg web</code> is running.
          </p>
          <div className="mt-8 flex justify-center">
            <Button
              onClick={async () => {
                setRetrying(true);
                const ok = await retryHealthCheck();
                setRetrying(false);
                if (!ok) {
                  toast.error('Could not connect to Kagan server. Make sure kg web is running.');
                }
              }}
              disabled={retrying}
              className="w-full max-w-xs"
            >
              <RefreshCw className={`size-4 ${retrying ? 'animate-spin' : ''}`} />
              {retrying ? 'Connecting...' : 'Retry connection'}
            </Button>
          </div>
        </div>
      </div>
    );
  }

  if (loading) {
    return (
      <div className="flex h-screen items-center justify-center bg-[color:var(--surface-0)]">
        <div className="h-8 w-32 animate-pulse bg-[var(--muted)]" />
      </div>
    );
  }

  const isEmpty = projects.length === 0;

  return (
    <div className="flex min-h-screen flex-col items-center bg-[color:var(--surface-0)] px-4 py-16 sm:px-6">
      <div className="w-full max-w-xl">
        {/* Logo */}
        <div className="mb-6 text-center">
          <span className="inline-flex items-center gap-1.5 bg-[color:var(--surface-1)] px-3 py-1.5 shadow-[var(--ambient-shadow)]">
            <span className="font-code text-sm tracking-[0.08em]">ᘚᘛ</span>
            <span className="font-code text-xs font-semibold uppercase tracking-[0.22em]">Kagan</span>
          </span>
        </div>

        {/* Actions */}
        <div className="mb-8 flex justify-center gap-3">
          <Button onClick={() => setCreateOpen(true)} className="">
            <Plus className="size-4" />
            New Project
          </Button>
          <Button variant="outline" className="" onClick={() => setFolderPickerOpen(true)}>
            <FolderOpen className="size-4" />
            Open Folder
          </Button>
        </div>

        {/* Project list */}
        {isEmpty ? (
          <div className=" bg-[color:var(--surface-1)] p-8 text-center shadow-[var(--ambient-shadow)]">
            <FolderGit2 className="mx-auto mb-3 size-8 text-[var(--muted-foreground)]" />
            <h2 className="mb-1.5 text-sm font-semibold">Welcome to Kagan</h2>
            <p className="text-xs text-[var(--muted-foreground)]">
              Create a new project or open an existing repository folder to get started.
            </p>
          </div>
        ) : (
          <div className="space-y-2">
            <p className="px-1 font-code text-[11px] uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
              Recent Projects
            </p>
            <div className="divide-y divide-[color:var(--border-subtle)] bg-[color:var(--surface-1)] shadow-[var(--ambient-shadow)]">
              {projects.map(({ project, repos }, index) => (
                <div key={project.id}>
                  <div
                    className={`group flex items-center gap-4 px-5 py-4 transition-colors hover:bg-[color:var(--surface-2)] ${project.active ? 'border-l-2 border-l-[var(--primary)] bg-[color:var(--surface-2)]' : ''}`}
                  >
                    <button
                      type="button"
                      onClick={() => handleOpenProject({ project, repos })}
                      className="flex min-w-0 flex-1 items-center gap-4 text-left"
                    >
                      <span className="flex size-7 shrink-0 items-center justify-center bg-[color:var(--surface-2)] font-code text-xs text-[var(--muted-foreground)]">
                        {index < 9 ? index + 1 : ''}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-semibold">
                          {project.name}
                          {project.active && (
                            <span className="ml-2 inline-block bg-[var(--primary)] px-1.5 py-0.5 font-code text-[9px] uppercase tracking-[0.16em] text-[var(--primary-foreground)]">Active</span>
                          )}
                        </p>
                        <p className="mt-0.5 text-xs text-[var(--muted-foreground)]">
                          {repos.length} repo{repos.length !== 1 ? 's' : ''}
                          {repos[0] ? ` \u00B7 ${repos[0].default_branch}` : ''}
                        </p>
                      </div>
                    </button>
                    <Button
                      variant="ghost"
                      size="icon-xs"
                      onClick={(e) => {
                        e.stopPropagation();
                        setDeleteTarget({ project, repos });
                      }}
                      className="opacity-0 transition-opacity group-hover:opacity-100"
                      aria-label={`Delete ${project.name}`}
                      title="Delete project"
                    >
                      <Trash2 className="size-3.5 text-[var(--destructive)]" />
                    </Button>
                  </div>
                  {expandedProjectId === project.id && repos.length > 1 && (
                    <div className="space-y-1 border-t border-[color:var(--border-subtle)] bg-[color:var(--surface-0)] px-5 py-3">
                      <p className="text-[10px] font-medium uppercase tracking-wider text-[var(--muted-foreground)]">
                        Select repository
                      </p>
                      {repos.map((repo) => (
                        <button
                          key={repo.id}
                          type="button"
                          onClick={() => handleSelectRepo(project, repo)}
                          className="flex w-full items-center gap-2 px-2 py-1.5 text-left text-xs text-[var(--foreground)] transition-colors hover:bg-[var(--muted)]"
                        >
                          <GitBranch className="size-3 text-[var(--muted-foreground)]" />
                          <span className="flex-1 truncate">{repo.name}</span>
                          <span className="text-[10px] text-[var(--muted-foreground)]">{repo.default_branch}</span>
                        </button>
                      ))}
                    </div>
                  )}
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Keyboard hints */}
        {!isEmpty && (
          <p className="mt-6 text-center text-xs text-[var(--muted-foreground)]">
            Press <kbd className=" bg-[color:var(--surface-2)] px-1.5 py-0.5 font-code text-[10px]">1</kbd>-<kbd className=" bg-[color:var(--surface-2)] px-1.5 py-0.5 font-code text-[10px]">9</kbd> to quick-open a project
          </p>
        )}
      </div>

      {/* Create project dialog */}
      <Dialog open={createOpen} onOpenChange={setCreateOpen}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>New Project</DialogTitle>
            <DialogDescription>
              Create a new project and optionally attach a repository.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="mb-1.5 block text-sm font-medium" htmlFor="project-name">
                Project name
              </label>
              <Input
                id="project-name"
                value={newName}
                onChange={(e) => setNewName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
                placeholder="my-project"
                autoFocus
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium" htmlFor="repo-path">
                Repository path <span className="text-[var(--muted-foreground)]">(optional)</span>
              </label>
              <div className="flex items-center gap-2">
                <Input
                  id="repo-path"
                  value={newRepoPath}
                  onChange={(e) => setNewRepoPath(e.target.value)}
                  placeholder="/path/to/repository"
                  className="flex-1 font-mono text-sm"
                />
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  onClick={() => setRepoPickerOpen(true)}
                  title="Browse filesystem"
                >
                  <FolderOpen className="size-4" />
                </Button>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCreateOpen(false)} disabled={creating}>
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={!newName.trim() || creating}>
              {creating ? 'Creating...' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Repo picker for new project */}
      <PathPicker
        open={repoPickerOpen}
        onOpenChange={setRepoPickerOpen}
        onSelect={(selected) => {
          setNewRepoPath(selected);
          // Auto-fill name from folder if empty
          if (!newName.trim()) {
            const folderName = selected.split('/').filter(Boolean).at(-1) ?? '';
            setNewName(folderName);
          }
        }}
        title="Select repository"
        description="Navigate to a git repository on the server filesystem."
        gitOnly
      />

      {/* Folder picker for "Open Folder" */}
      <PathPicker
        open={folderPickerOpen}
        onOpenChange={setFolderPickerOpen}
        onSelect={handleOpenFolder}
        title="Open folder"
        description="Select a repository folder to open as a project."
        gitOnly
      />

      {/* Delete confirmation */}
      <AlertDialog open={!!deleteTarget} onOpenChange={(open) => !open && setDeleteTarget(null)}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Delete project?</AlertDialogTitle>
            <AlertDialogDescription>
              This will permanently delete <strong>{deleteTarget?.project.name}</strong> and all its tasks. This action cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction onClick={handleDelete} className="bg-[var(--destructive)] text-[var(--destructive-foreground)] hover:bg-[var(--destructive)]/90">
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </div>
  );
}
