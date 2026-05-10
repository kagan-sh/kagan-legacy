import { useEffect, useState } from 'react';
import { useSetAtom } from 'jotai';
import { FolderOpen, Plus } from 'lucide-react';
import { apiClient } from '@/lib/api/client';
import { projectSwitchVersionAtom } from '@/lib/atoms/board';
import {
  createProjectDialogOpenAtom,
  addRepoDialogOpenAtom,
} from '@/lib/atoms/shell';
import { useActiveProject } from '@/lib/hooks/use-active-project';
import {
  PopoverPanel,
  PopoverTitle,
  PopoverItem,
  PopoverSeparator,
  useShellPopover,
} from '../popover';
import type { WireProject } from '@kagan/shared-api-client';

export function ProjectSwitcherPopover() {
  const { isOpen, close } = useShellPopover('project-switcher', 'left');
  const [projects, setProjects] = useState<WireProject[]>([]);
  const activeProject = useActiveProject();
  const bumpVersion = useSetAtom(projectSwitchVersionAtom);
  const setCreateOpen = useSetAtom(createProjectDialogOpenAtom);
  const setAddRepoOpen = useSetAtom(addRepoDialogOpenAtom);

  // Fetch project list whenever the popover opens
  useEffect(() => {
    if (!isOpen) return;
    let cancelled = false;
    apiClient
      .getProjects()
      .then((list) => {
        if (!cancelled) setProjects(list);
      })
      .catch(() => {});
    return () => {
      cancelled = true;
    };
  }, [isOpen]);

  const handleActivate = async (id: string) => {
    if (id === activeProject?.id) {
      close();
      return;
    }
    try {
      await apiClient.activateProject(id);
      bumpVersion((v) => v + 1);
    } catch {
      // activation errors are non-fatal; board will stay on current project
    }
    close();
  };

  const handleNewProject = () => {
    close();
    setCreateOpen(true);
  };

  const handleAddRepo = () => {
    close();
    setAddRepoOpen(true);
  };

  // Show "Add repository" only when the active project has no repos attached.
  // We check by attempting to list repos; fall back to hiding the action.
  const [hasRepo, setHasRepo] = useState<boolean | null>(null);

  useEffect(() => {
    if (!isOpen || !activeProject) {
      setHasRepo(null);
      return;
    }
    let cancelled = false;
    apiClient
      .getProjectRepos(activeProject.id)
      .then((repos) => {
        if (!cancelled) setHasRepo(repos.length > 0);
      })
      .catch(() => {
        if (!cancelled) setHasRepo(true); // assume has repo on error to avoid false positive
      });
    return () => {
      cancelled = true;
    };
  }, [isOpen, activeProject]);

  return (
    <PopoverPanel kind="project-switcher" minWidth={240}>
      <PopoverTitle>Project</PopoverTitle>

      {projects.length === 0 ? (
        <p className="px-2.5 py-3 font-code text-[11px] text-[var(--muted-foreground)]">
          Loading…
        </p>
      ) : (
        projects.map((project) => (
          <PopoverItem
            key={project.id}
            icon={<FolderOpen strokeWidth={1.75} className="size-[14px]" />}
            label={project.name}
            active={project.id === activeProject?.id}
            onClick={() => handleActivate(project.id)}
          />
        ))
      )}

      <PopoverSeparator />

      <PopoverItem
        icon={<Plus strokeWidth={1.75} className="size-[14px]" />}
        label="New project"
        onClick={handleNewProject}
      />

      {hasRepo === false ? (
        <PopoverItem
          icon={<FolderOpen strokeWidth={1.75} className="size-[14px]" />}
          label="Add repository"
          onClick={handleAddRepo}
        />
      ) : null}
    </PopoverPanel>
  );
}
