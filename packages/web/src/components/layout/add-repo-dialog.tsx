import { useState, useCallback } from 'react';
import { FolderOpen } from 'lucide-react';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api/client';
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

interface AddRepoDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  projectId: string | undefined;
  onAdded: () => void;
}

export function AddRepoDialog({ open, onOpenChange, projectId, onAdded }: AddRepoDialogProps) {
  const [path, setPath] = useState('');
  const [adding, setAdding] = useState(false);
  const [pickerOpen, setPickerOpen] = useState(false);

  const handleAdd = useCallback(async () => {
    const trimmed = path.trim();
    if (!trimmed || !projectId || adding) return;
    setAdding(true);
    try {
      const added = await apiClient.addProjectRepo(projectId, trimmed);
      const repoList = await apiClient.getProjectRepos(projectId);
      if (!repoList.some((r) => r.selected)) {
        await apiClient.selectProjectRepo(projectId, added.id);
      }
      onOpenChange(false);
      setPath('');
      toast.success('Repository added');
      onAdded();
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Failed to add repository');
    } finally {
      setAdding(false);
    }
  }, [path, projectId, adding, onOpenChange, onAdded]);

  return (
    <>
      <Dialog open={open} onOpenChange={onOpenChange}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>Add repository</DialogTitle>
            <DialogDescription>
              Browse to select a git repository on the server, or enter a path manually.
            </DialogDescription>
          </DialogHeader>
          <div className="flex items-center gap-2">
            <Input
              value={path}
              onChange={(e) => setPath(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && handleAdd()}
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
          <DialogFooter>
            <Button variant="outline" onClick={() => onOpenChange(false)} disabled={adding}>
              Cancel
            </Button>
            <Button onClick={handleAdd} disabled={!path.trim() || adding}>
              {adding ? 'Adding...' : 'Add'}
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      <PathPicker
        open={pickerOpen}
        onOpenChange={setPickerOpen}
        onSelect={(selected) => setPath(selected)}
        title="Select repository"
        description="Navigate to a git repository on the server filesystem."
        gitOnly
      />
    </>
  );
}
