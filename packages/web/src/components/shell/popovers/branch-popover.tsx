/**
 * Branch picker popover.
 *
 * Allows the user to select a base branch for the next task action.
 *
 * Branch data source: the server has no dedicated /repos/:id/branches endpoint
 * yet, so we synthesise the list from:
 *   1. The value already in composerBranchAtom (if any — keeps it in the list).
 *   2. 'main' (always present as the universal fallback).
 *   3. All distinct base_branch values from in-flight tasks in tasksAtom.
 *
 * TODO: replace this local synthesis with a real API call once
 *       GET /api/projects/:projectId/repos/:repoId/branches is available.
 */

import { useMemo } from 'react';
import { Copy, GitBranch } from 'lucide-react';
import { toast } from 'sonner';
import { useAtom, useAtomValue } from 'jotai';
import { tasksAtom } from '@/lib/atoms/board';
import { composerBranchAtom } from '@/lib/atoms/shell';
import { PopoverPanel, PopoverItem, useShellPopover } from '../popover';

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

function buildBranchList(
  tasks: ReturnType<typeof useAtomValue<typeof tasksAtom>>,
  selectedBranch: string | null,
): string[] {
  const seen = new Set<string>();
  const branches: string[] = [];

  const add = (b: string | null | undefined) => {
    if (b && !seen.has(b)) {
      seen.add(b);
      branches.push(b);
    }
  };

  // Always surface main first
  add('main');

  // Branches referenced by known tasks
  for (const task of tasks) {
    add(task.base_branch);
  }

  // If the current selection is not in the list (e.g. set externally) add it
  add(selectedBranch);

  return branches;
}

// ---------------------------------------------------------------------------
// Component
// ---------------------------------------------------------------------------

export function BranchPopover() {
  const [selectedBranch, setSelectedBranch] = useAtom(composerBranchAtom);
  const tasks = useAtomValue(tasksAtom);
  const { close } = useShellPopover('branch', 'left');

  const branches = useMemo(
    () => buildBranchList(tasks, selectedBranch),
    [tasks, selectedBranch],
  );

  const handleCopy = async () => {
    const label = selectedBranch ?? 'main';
    try {
      await navigator.clipboard.writeText(label);
      toast.success(`Copied: ${label}`);
    } catch {
      toast.error('Clipboard unavailable');
    }
  };

  const handleSelect = (branch: string) => {
    setSelectedBranch(branch);
    close();
  };

  return (
    <PopoverPanel kind="branch" minWidth={240}>
      {/* Header row: title + copy button */}
      <div className="flex items-center justify-between px-2.5 pb-2 pt-1.5">
        <span className="font-code text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
          Base branch
        </span>
        <button
          type="button"
          aria-label="Copy branch name"
          data-testid="branch-popover-copy-btn"
          onClick={() => { void handleCopy(); }}
          className="grid size-5 place-items-center rounded text-[var(--muted-foreground)] transition-colors hover:bg-[var(--surface-2)] hover:text-[var(--fg)]"
        >
          <Copy className="size-3" />
        </button>
      </div>

      {branches.map((branch) => (
        <PopoverItem
          key={branch}
          icon={<GitBranch className="size-3" strokeWidth={1.8} />}
          label={branch}
          active={branch === (selectedBranch ?? 'main')}
          onClick={() => handleSelect(branch)}
        />
      ))}
    </PopoverPanel>
  );
}
