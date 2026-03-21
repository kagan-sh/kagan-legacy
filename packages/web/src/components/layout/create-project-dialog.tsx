import { useState, useCallback } from 'react';
import { FolderOpen } from 'lucide-react';
import { toast } from 'sonner';
import { useSetAtom } from 'jotai';
import { apiClient } from '@/lib/api/client';
import type { WireProject } from '@/lib/api/types';
import { projectSwitchVersionAtom } from '@/lib/atoms/board';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { PathPicker } from '@/components/shared/path-picker';

interface CreateProjectDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onCreated: (project: WireProject) => void;
}

export function CreateProjectDialog({ open, onOpenChange, onCreated }: CreateProjectDialogProps) {
  const [name, setName] = useState('');
  const [repoPath, setRepoPath] = useState('');
  const [creating, setCreating] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);
  const bumpProjectVersion = useSetAtom(projectSwitchVersionAtom);

  const handleCreate = useCallback(async () => {
    const trimmed = name.trim();
    if (!trimmed || creating) return;
    setCreating(true);
    try {
      const created = await apiClient.createProject(trimmed);
      if (repoPath.trim()) {
        const repo = await apiClient.addProjectRepo(created.id, repoPath.trim());
        await apiClient.selectProjectRepo(created.id, repo.id);
      }
      await apiClient.activateProject(created.id);
      bumpProjectVersion((v) => v + 1);
      onOpenChange(false);
      setName('');
      setRepoPath('');
      toast.success(`Created ${created.name}`);
      onCreated(created);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to create project');
    } finally {
      setCreating(false);
    }
  }, [name, repoPath, creating, bumpProjectVersion, onOpenChange, onCreated]);

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Create project</DialogTitle>
            <DialogDescription>
              Create a new project and optionally attach a repository.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4">
            <div>
              <label className="mb-1.5 block text-sm font-medium" htmlFor="cp-name">
                Project name
              </label>
              <Input
                id="cp-name"
                value={name}
                onChange={(e) => setName(e.target.value)}
                onKeyDown={(e) => e.key === 'Enter' && handleCreate()}
                placeholder="my-project"
                autoFocus
              />
            </div>
            <div>
              <label className="mb-1.5 block text-sm font-medium" htmlFor="cp-repo">
                Repository path <span className="text-[var(--muted-foreground)]">(optional)</span>
              </label>
              <div className="flex items-center gap-2">
                <Input
                  id="cp-repo"
                  value={repoPath}
                  onChange={(e) => setRepoPath(e.target.value)}
                  placeholder="/path/to/repository"
                  className="flex-1 font-mono text-sm"
                />
                <Button
                  type="button"
                  variant="outline"
                  size="icon"
                  onClick={() => setPickerOpen(true)}
                  title="Browse filesystem"
                >
                  <FolderOpen className="size-4" />
                </Button>
              </div>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={creating}>
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={!name.trim() || creating}>
              {creating ? 'Creating...' : 'Create'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <PathPicker
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        onSelect={(selected) => {
          setRepoPath(selected);
          if (!name.trim()) {
            const folderName = selected.split('/').filter(Boolean).at(-1) ?? '';
            setName(folderName);
          }
        }}
        title="Select repository"
        description="Navigate to a git repository on the server filesystem."
        gitOnly
      />
    </>
  );
}
