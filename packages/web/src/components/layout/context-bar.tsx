import { useCallback, useEffect, useState } from 'react';
import { FolderKanban, GitBranch, Plus, Trash2 } from 'lucide-react';
import { useSetAtom } from 'jotai';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api/client';
import type { WireProject, WireRepository } from '@kagan/shared-api-client';
import { boardRepoFilterAtom, projectSwitchVersionAtom } from '@/lib/atoms/board';
import { CreateProjectDialog } from '@/components/layout/create-project-dialog';
import { AddRepoDialog } from '@/components/layout/add-repo-dialog';
import { Button } from '@/components/ui/button';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectSeparator,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
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

// ---------------------------------------------------------------------------
// ContextBar — project + repo selectors for the header
// ---------------------------------------------------------------------------

export function ContextBar() {
  const [projects, setProjects] = useState<WireProject[]>([]);
  const [repos, setRepos] = useState<WireRepository[]>([]);
  const [loading, setLoading] = useState(true);

  const [createProjectOpen, setCreateProjectOpen] = useState(false);
  const [addRepoOpen, setAddRepoOpen] = useState(false);
  const [deleteProjectOpen, setDeleteProjectOpen] = useState(false);
  const [deleteRepoOpen, setDeleteRepoOpen] = useState(false);

  const bumpProjectVersion = useSetAtom(projectSwitchVersionAtom);
  const setRepoFilter = useSetAtom(boardRepoFilterAtom);

  const activeProject = projects.find((p) => p.active) ?? null;
  const activeRepo = repos.find((r) => r.selected) ?? null;

  // -- Loaders ---------------------------------------------------------------

  const loadProjects = useCallback(async () => {
    try {
      const data = await apiClient.getProjects();
      setProjects(data);
      return data;
    } catch {
      toast.error('Failed to load projects');
      return [];
    }
  }, []);

  const loadRepos = useCallback(async (projectId: string) => {
    try {
      const data = await apiClient.getProjectRepos(projectId);
      setRepos(data);
      return data;
    } catch {
      setRepos([]);
      return [];
    }
  }, []);

  /**
   * After switching project, auto-select the first repo if none is selected.
   * Mirrors TUI behaviour in KaganApp.activate_project().
   */
  const ensureRepoSelected = useCallback(
    async (projectId: string, repoList: WireRepository[]) => {
      const hasSelected = repoList.some((r) => r.selected);
      const firstRepo = repoList[0];
      if (!hasSelected && firstRepo) {
        try {
          await apiClient.selectProjectRepo(projectId, firstRepo.id);
          await loadRepos(projectId);
        } catch {
          // best-effort
        }
      } else if (!hasSelected && repoList.length === 0) {
        setAddRepoOpen(true);
      }
    },
    [loadRepos],
  );

  useEffect(() => {
    const init = async () => {
      const data = await loadProjects();
      const active = data.find((p) => p.active);
      if (active) {
        const repoList = await loadRepos(active.id);
        await ensureRepoSelected(active.id, repoList);
      }
      setLoading(false);
    };
    init();
  }, [loadProjects, loadRepos, ensureRepoSelected]);

  // -- Handlers --------------------------------------------------------------

  const handleProjectChange = useCallback(
    async (projectId: string) => {
      if (projectId === '__create__') {
        setCreateProjectOpen(true);
        return;
      }
      try {
        await apiClient.activateProject(projectId);
        const data = await loadProjects();
        const proj = data.find((p) => p.id === projectId);
        if (proj) {
          const repoList = await loadRepos(proj.id);
          await ensureRepoSelected(proj.id, repoList);
        }
        bumpProjectVersion((v) => v + 1);
        toast.success(`Switched to ${proj?.name ?? 'project'}`);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'Failed to switch project');
      }
    },
    [loadProjects, loadRepos, ensureRepoSelected, bumpProjectVersion],
  );

  const handleRepoChange = useCallback(
    async (repoId: string) => {
      if (repoId === '__add__') {
        setAddRepoOpen(true);
        return;
      }
      if (!activeProject) return;
      try {
        await apiClient.selectProjectRepo(activeProject.id, repoId);
        await loadRepos(activeProject.id);
        setRepoFilter(repoId);
        bumpProjectVersion((v) => v + 1);
      } catch (error) {
        toast.error(error instanceof Error ? error.message : 'Failed to select repo');
      }
    },
    [activeProject, loadRepos, setRepoFilter, bumpProjectVersion],
  );

  const handleProjectCreated = useCallback(
    async (created: WireProject) => {
      await loadProjects();
      const repoList = await loadRepos(created.id);
      await ensureRepoSelected(created.id, repoList);
    },
    [loadProjects, loadRepos, ensureRepoSelected],
  );

  const handleRepoAdded = useCallback(async () => {
    if (activeProject) {
      const repoList = await loadRepos(activeProject.id);
      const selected = repoList.find((r) => r.selected);
      if (selected) setRepoFilter(selected.id);
      bumpProjectVersion((v) => v + 1);
    }
  }, [activeProject, loadRepos, setRepoFilter, bumpProjectVersion]);

  const handleDeleteProject = useCallback(async () => {
    if (!activeProject) return;
    try {
      await apiClient.deleteProject(activeProject.id);
      const data = await loadProjects();
      const nextActive = data.find((p) => p.active);
      if (nextActive) {
        await loadRepos(nextActive.id);
      } else {
        setRepos([]);
      }
      bumpProjectVersion((v) => v + 1);
      toast.success(`Deleted project "${activeProject.name}"`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to delete project');
    } finally {
      setDeleteProjectOpen(false);
    }
  }, [activeProject, loadProjects, loadRepos, bumpProjectVersion]);

  const handleDeleteRepo = useCallback(async () => {
    if (!activeProject || !activeRepo) return;
    try {
      await apiClient.deleteProjectRepo(activeProject.id, activeRepo.id);
      await loadRepos(activeProject.id);
      toast.success(`Removed repository "${activeRepo.name}"`);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to remove repository');
    } finally {
      setDeleteRepoOpen(false);
    }
  }, [activeProject, activeRepo, loadRepos]);

  // -- Render ----------------------------------------------------------------

  if (loading) {
    return <span className="text-xs text-[var(--muted-foreground)]">Loading...</span>;
  }

  return (
    <>
      <div className="flex items-center gap-2">
        {/* Project selector */}
        <div className="flex items-center gap-1">
          <Select value={activeProject?.id ?? ''} onValueChange={handleProjectChange}>
            <SelectTrigger size="sm" className="h-8 gap-1.5 text-xs">
              <FolderKanban className="size-3.5 text-[var(--muted-foreground)]" />
              <SelectValue placeholder="Select project" />
            </SelectTrigger>
            <SelectContent>
              {projects.map((project) => (
                <SelectItem key={project.id} value={project.id}>
                  {project.name}
                </SelectItem>
              ))}
              {projects.length > 0 && <SelectSeparator />}
              <SelectItem value="__create__">
                <Plus className="size-3.5" />
                New project...
              </SelectItem>
            </SelectContent>
          </Select>
          {activeProject && (
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => setDeleteProjectOpen(true)}
              aria-label="Delete project"
            >
              <Trash2 className="size-3 text-[var(--muted-foreground)]" />
            </Button>
          )}
        </div>

        {/* Repo selector */}
        <div className="flex items-center gap-1">
          <Select
            value={activeRepo?.id ?? ''}
            onValueChange={handleRepoChange}
            disabled={!activeProject}
          >
            <SelectTrigger size="sm" className="h-8 gap-1.5 text-xs">
              <GitBranch className="size-3.5 text-[var(--muted-foreground)]" />
              <SelectValue placeholder={activeProject ? 'Select repo' : 'No project'} />
            </SelectTrigger>
            <SelectContent>
              {repos.map((repo) => (
                <SelectItem key={repo.id} value={repo.id}>
                  <span className="truncate">{repo.name}</span>
                  <span className="ml-1.5 text-[10px] text-[var(--muted-foreground)]">
                    {repo.default_branch}
                  </span>
                </SelectItem>
              ))}
              {repos.length > 0 && <SelectSeparator />}
              <SelectItem value="__add__">
                <Plus className="size-3.5" />
                Add repository...
              </SelectItem>
            </SelectContent>
          </Select>
          {activeRepo && (
            <Button
              variant="ghost"
              size="icon-sm"
              onClick={() => setDeleteRepoOpen(true)}
              aria-label="Remove repository"
            >
              <Trash2 className="size-3 text-[var(--muted-foreground)]" />
            </Button>
          )}
        </div>
      </div>

      {/* Delete project confirmation */}
      <AlertDialog open={deleteProjectOpen} onOpenChange={setDeleteProjectOpen}>
        <AlertDialogContent size="sm">
          <AlertDialogHeader>
            <AlertDialogTitle>Delete project &ldquo;{activeProject?.name}&rdquo;?</AlertDialogTitle>
            <AlertDialogDescription>
              This will remove the project and all its repos. This cannot be undone.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={handleDeleteProject}>
              Delete
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      {/* Remove repo confirmation */}
      <AlertDialog open={deleteRepoOpen} onOpenChange={setDeleteRepoOpen}>
        <AlertDialogContent size="sm">
          <AlertDialogHeader>
            <AlertDialogTitle>Remove repository &ldquo;{activeRepo?.name}&rdquo;?</AlertDialogTitle>
            <AlertDialogDescription>
              The repository will be unlinked from this project.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel>Cancel</AlertDialogCancel>
            <AlertDialogAction variant="destructive" onClick={handleDeleteRepo}>
              Remove
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>

      <CreateProjectDialog
        open={createProjectOpen}
        onOpenChange={setCreateProjectOpen}
        onCreated={handleProjectCreated}
      />

      <AddRepoDialog
        open={addRepoOpen}
        onOpenChange={setAddRepoOpen}
        projectId={activeProject?.id}
        onAdded={handleRepoAdded}
      />
    </>
  );
}
