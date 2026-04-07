import { useCallback, useEffect, useState } from 'react';
import { Download, ArrowLeft } from 'lucide-react';
import { toast } from 'sonner';
import { apiClient } from '@/lib/api/client';
import {
  Dialog, DialogContent, DialogDescription, DialogFooter,
  DialogHeader, DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Button } from '@/components/ui/button';
import { Spinner } from '@/components/ui/spinner';

interface GitHubIssuePreview {
  number: number;
  title: string;
  state: string;
  labels: string[];
  url: string;
  already_synced: boolean;
}

interface PluginImportDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
}

export function PluginImportDialog({ open, onOpenChange }: PluginImportDialogProps) {
  // Filter state
  const [repo, setRepo] = useState('');
  const [state, setState] = useState<'open' | 'closed' | 'all'>('open');
  const [labels, setLabels] = useState('');
  const [limit, setLimit] = useState(100);
  const [ready, setReady] = useState<boolean | null>(null);
  const [preflightMsg, setPreflightMsg] = useState('');
  const [detecting, setDetecting] = useState(false);

  // Preview state
  const [step, setStep] = useState<'filter' | 'select'>('filter');
  const [issues, setIssues] = useState<GitHubIssuePreview[]>([]);
  const [selected, setSelected] = useState<Set<number>>(new Set());
  const [previewing, setPreviewing] = useState(false);
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
    setRepo(''); setState('open'); setLabels(''); setLimit(100);
    setReady(null); setPreflightMsg('');
    setStep('filter'); setIssues([]); setSelected(new Set());
    void detect();
  }, [open, detect]);

  const handlePreview = async () => {
    if (!repo.trim()) { toast.error('Repository slug is required'); return; }
    setPreviewing(true);
    try {
      const result = await apiClient.previewPluginIssues('github', {
        repo_slug: repo.trim(),
        state,
        labels: labels.trim() || undefined,
        limit,
      });
      setIssues(result.issues);
      // Auto-select non-synced issues
      setSelected(new Set(result.issues.filter((i) => !i.already_synced).map((i) => i.number)));
      setStep('select');
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Preview failed');
    } finally {
      setPreviewing(false);
    }
  };

  const handleImport = async () => {
    if (selected.size === 0) return;
    setImporting(true);
    try {
      const config: Record<string, unknown> = {
        repo_slug: repo.trim(),
        state,
        issue_numbers: Array.from(selected),
        limit,
      };
      if (labels.trim()) config.labels = labels.trim().split(',').map((l) => l.trim());
      const result = await apiClient.runPluginImport('github', config);
      const parts: string[] = [];
      if (result.created > 0) parts.push(`${result.created} created`);
      if (result.skipped > 0) parts.push(`${result.skipped} skipped`);
      if (result.errors.length > 0) parts.push(`${result.errors.length} errors`);
      toast.success(parts.length > 0 ? parts.join(', ') : 'Import complete');
      onOpenChange(false);
    } catch (error) {
      toast.error(error instanceof Error ? error.message : 'Import failed');
    } finally {
      setImporting(false);
    }
  };

  const toggleIssue = (num: number) => {
    setSelected((prev) => {
      const next = new Set(prev);
      if (next.has(num)) next.delete(num); else next.add(num);
      return next;
    });
  };

  const syncedCount = issues.filter((i) => i.already_synced).length;

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Download className="size-4" />
            Import from GitHub
          </DialogTitle>
          <DialogDescription>
            {step === 'filter'
              ? 'Configure filters, then preview matching issues.'
              : `${issues.length} issues found${syncedCount > 0 ? ` (${syncedCount} already synced)` : ''}`}
          </DialogDescription>
        </DialogHeader>

        {step === 'filter' ? (
          <div className="space-y-4">
            {/* Preflight indicator */}
            <div className="flex items-center gap-2 text-xs">
              {detecting ? (
                <><Spinner className="size-3" /><span className="text-[var(--muted-foreground)]">Detecting repository…</span></>
              ) : ready === true ? (
                <><span className="inline-block size-2 rounded-full bg-[var(--kagan-rail-running)]" /><span className="text-[var(--muted-foreground)]">GitHub plugin ready</span></>
              ) : ready === false ? (
                <><span className="inline-block size-2 rounded-full bg-amber-500" /><span className="text-[var(--muted-foreground)]">{preflightMsg}</span></>
              ) : null}
            </div>

            <div>
              <Label htmlFor="plugin-repo" className="mb-1">Repository</Label>
              <Input id="plugin-repo" value={repo} onChange={(e) => setRepo(e.target.value)} placeholder="owner/repo" className="font-mono text-sm" autoFocus />
            </div>

            <div className="flex gap-4">
              <div className="flex-1">
                <Label htmlFor="plugin-state" className="mb-1">State</Label>
                <NativeSelect id="plugin-state" value={state} onChange={(e) => setState(e.target.value as 'open' | 'closed' | 'all')} className="w-full">
                  <NativeSelectOption value="open">Open</NativeSelectOption>
                  <NativeSelectOption value="closed">Closed</NativeSelectOption>
                  <NativeSelectOption value="all">All</NativeSelectOption>
                </NativeSelect>
              </div>
              <div className="flex-1">
                <Label htmlFor="plugin-labels" className="mb-1">Labels</Label>
                <Input id="plugin-labels" value={labels} onChange={(e) => setLabels(e.target.value)} placeholder="bug, feature" />
              </div>
            </div>

            <div>
              <Label htmlFor="plugin-limit" className="mb-1">Limit</Label>
              <Input id="plugin-limit" type="number" min={1} max={500} value={limit} onChange={(e) => setLimit(Number(e.target.value) || 100)} className="w-24" />
            </div>
          </div>
        ) : (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <Button variant="ghost" size="sm" onClick={() => setStep('filter')}>
                <ArrowLeft className="size-3 mr-1" /> Filters
              </Button>
              <div className="flex gap-2">
                <Button variant="ghost" size="sm" onClick={() => setSelected(new Set(issues.map((i) => i.number)))}>Select all</Button>
                <Button variant="ghost" size="sm" onClick={() => setSelected(new Set())}>Deselect all</Button>
              </div>
            </div>

            <div className="max-h-72 overflow-y-auto space-y-1 border rounded-md p-2">
              {issues.map((issue) => (
                <label key={issue.number} className={`flex items-center gap-2 rounded px-2 py-1.5 text-sm cursor-pointer hover:bg-[var(--accent)] ${issue.already_synced ? 'opacity-50' : ''}`}>
                  <input
                    type="checkbox"
                    checked={selected.has(issue.number)}
                    onChange={() => toggleIssue(issue.number)}
                    className="size-4 shrink-0"
                  />
                  <span className="font-mono text-xs text-[var(--muted-foreground)]">#{issue.number}</span>
                  <span className="flex-1 truncate">{issue.title}</span>
                  {issue.labels.map((lbl) => (
                    <span key={lbl} className="text-[10px] px-1.5 py-0.5 rounded-full bg-[var(--accent)] text-[var(--accent-foreground)]">{lbl}</span>
                  ))}
                  {issue.already_synced && <span className="text-[10px] text-[var(--muted-foreground)]">(synced)</span>}
                </label>
              ))}
              {issues.length === 0 && <p className="text-sm text-[var(--muted-foreground)] text-center py-4">No issues match the filters.</p>}
            </div>
          </div>
        )}

        <DialogFooter>
          <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
          {step === 'filter' ? (
            <Button onClick={handlePreview} disabled={previewing || detecting || ready === false}>
              {previewing ? <><Spinner className="size-4 mr-1" /> Fetching…</> : 'Preview Issues'}
            </Button>
          ) : (
            <Button onClick={handleImport} disabled={importing || selected.size === 0}>
              <Download className="size-4" />
              {importing ? 'Importing…' : `Import ${selected.size} Selected`}
            </Button>
          )}
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
