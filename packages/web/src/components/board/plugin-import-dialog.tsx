import { useCallback, useEffect, useState } from 'react';
import { Download } from 'lucide-react';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api/client';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';

interface PluginImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function PluginImportDialog({ open, onOpenChange }: PluginImportDialogProps) {
  const [repo, setRepo] = useState('');
  const [state, setState] = useState<'open' | 'closed' | 'all'>('open');
  const [label, setLabel] = useState('');
  const [ready, setReady] = useState<boolean | null>(null);
  const [preflightMsg, setPreflightMsg] = useState('');
  const [detecting, setDetecting] = useState(false);
  const [importing, setImporting] = useState(false);

  const detect = useCallback(async () => {
    setDetecting(true);
    try {
      const [repoResult, preflight] = await Promise.all([
        apiClient.detectPluginRepo('github'),
        apiClient.getPluginPreflight('github'),
      ]);
      if (repoResult.repo_slug) setRepo(repoResult.repo_slug);
      setReady(preflight.ready);
      if (!preflight.ready) {
        const failing = preflight.checks.find((c) => !c.ok);
        setPreflightMsg(failing?.message ?? 'Plugin not ready');
      }
    } catch {
      setReady(null);
      setPreflightMsg('Could not reach plugin API');
    } finally {
      setDetecting(false);
    }
  }, []);

  useEffect(() => {
    if (!open) return;
    setRepo('');
    setState('open');
    setLabel('');
    setReady(null);
    setPreflightMsg('');
    void detect();
  }, [open, detect]);

  const handleImport = async () => {
    if (!repo.trim()) {
      toast.error('Repository slug is required');
      return;
    }
    setImporting(true);
    try {
      const config: Record<string, unknown> = {
        repo: repo.trim(),
        state,
      };
      if (label.trim()) config.labels = label.trim();
      const result = await apiClient.runPluginImport('github', config);
      const parts: string[] = [];
      if (result.created > 0) parts.push(`${result.created} created`);
      if (result.updated > 0) parts.push(`${result.updated} updated`);
      if (result.skipped > 0) parts.push(`${result.skipped} skipped`);
      if (result.errors.length > 0) parts.push(`${result.errors.length} errors`);
      toast.success(parts.length > 0 ? parts.join(', ') : 'Import complete');
      if (result.errors.length > 0) {
        toast.error(result.errors.slice(0, 3).join('\n'));
      }
      onOpenChange(false);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Import failed');
    } finally {
      setImporting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-md">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Download className="size-4" />
            Import from GitHub
          </DialogTitle>
          <DialogDescription>
            Import issues from a GitHub repository as tasks.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {/* Preflight indicator */}
          <div className="flex items-center gap-2 text-xs">
            {detecting ? (
              <>
                <Spinner className="size-3" />
                <span className="text-[var(--muted-foreground)]">Detecting repository…</span>
              </>
            ) : ready === true ? (
              <>
                <span className="inline-block size-2 rounded-full bg-[var(--kagan-rail-running)]" />
                <span className="text-[var(--muted-foreground)]">GitHub plugin ready</span>
              </>
            ) : ready === false ? (
              <>
                <span className="inline-block size-2 rounded-full bg-amber-500" />
                <span className="text-[var(--muted-foreground)]">{preflightMsg}</span>
              </>
            ) : null}
          </div>

          {/* Repo slug */}
          <div>
            <Label htmlFor="plugin-repo" className="mb-1">Repository</Label>
            <Input
              id="plugin-repo"
              value={repo}
              onChange={(e) => setRepo(e.target.value)}
              placeholder="owner/repo"
              className="font-mono text-sm"
              autoFocus
            />
          </div>

          {/* State filter */}
          <div className="flex gap-4">
            <div className="flex-1">
              <Label htmlFor="plugin-state" className="mb-1">State</Label>
              <NativeSelect
                id="plugin-state"
                value={state}
                onChange={(e) => setState(e.target.value as 'open' | 'closed' | 'all')}
                className="w-full"
              >
                <NativeSelectOption value="open">Open</NativeSelectOption>
                <NativeSelectOption value="closed">Closed</NativeSelectOption>
                <NativeSelectOption value="all">All</NativeSelectOption>
              </NativeSelect>
            </div>
            <div className="flex-1">
              <Label htmlFor="plugin-label" className="mb-1">Label filter</Label>
              <Input
                id="plugin-label"
                value={label}
                onChange={(e) => setLabel(e.target.value)}
                placeholder="e.g. bug"
              />
            </div>
          </div>
        </div>

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button onClick={handleImport} disabled={importing || detecting || ready === false}>
            <Download className="size-4" />
            {importing ? 'Importing…' : 'Import'}
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
