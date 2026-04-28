import { useAtom } from 'jotai';
import { atomWithStorage } from 'jotai/utils';
import { launcherDisplayName, type LauncherBackend } from '@/lib/utils/editor-links';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Switch } from '@/components/ui/switch';

// Persisted atom: user opted out of seeing this dialog again
export const skipAttachedGuidanceAtom = atomWithStorage<boolean>(
  'kagan:skip-attached-guidance',
  false,
);

interface AttachedInstructionsDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  launcher: LauncherBackend;
  isRunningBackground: boolean;
  onContinue: (skipFuture: boolean) => void;
}

export function AttachedInstructionsDialog({
  open,
  onOpenChange,
  launcher,
  isRunningBackground,
  onContinue,
}: AttachedInstructionsDialogProps) {
  const [skipFuture, setSkipFuture] = useAtom(skipAttachedGuidanceAtom);

  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent className="sm:max-w-xl">
        <DialogHeader>
          <DialogTitle>Interactive Session Instructions</DialogTitle>
          <DialogDescription>
            {isRunningBackground
              ? 'A background agent is running. It will be stopped and you will take over manually in your terminal/editor.'
              : 'We will start an interactive session, then you continue in your own terminal/editor using the task startup prompt.'}
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3 text-sm text-[var(--muted-foreground)]">
          {launcher === 'tmux' ? (
            <>
              <p>You are about to enter a tmux-backed interactive session.</p>
              <ol className="list-decimal space-y-1 pl-5">
                <li>Press Continue to launch the agent session.</li>
                <li>A tmux attach command is copied to your clipboard.</li>
                <li>Open your terminal and paste the command to attach.</li>
                <li>Detach with <code>Ctrl+b d</code> to return to Kagan.</li>
              </ol>
            </>
          ) : launcher === 'nvim' ? (
            <>
              <p>Interactive attach will open Neovim with the startup prompt file.</p>
              <ol className="list-decimal space-y-1 pl-5">
                <li>Press Continue to prepare the interactive session.</li>
                <li>Neovim opens with <code>.kagan/start_prompt.md</code> in the task worktree.</li>
                <li>Copy the prompt contents and paste into your AI chat plugin.</li>
              </ol>
            </>
          ) : (
            <>
              <p>
                Interactive attach will open {launcherDisplayName(launcher)} in the task worktree.
                The startup prompt file will be open in your editor.
              </p>
              <ol className="list-decimal space-y-1 pl-5">
                <li>Press Continue to start the session.</li>
                <li>Kagan opens your editor in the task worktree with the startup prompt visible.</li>
                <li>Copy the prompt contents and paste into your IDE's AI chat.</li>
              </ol>
            </>
          )}

          <label className="flex items-center justify-between gap-3 rounded border border-[color:var(--border-subtle)] px-3 py-2">
            <span className="text-sm text-[var(--foreground)]">Do not show this guidance again</span>
            <Switch
              checked={skipFuture}
              onCheckedChange={(value) => setSkipFuture(Boolean(value))}
              aria-label="Do not show attached guidance again"
            />
          </label>
        </div>

        <DialogFooter>
          <Button variant="outline" onClick={() => onOpenChange(false)}>
            Cancel
          </Button>
          <Button
            onClick={() => {
              onOpenChange(false);
              onContinue(skipFuture);
            }}
          >
            Continue
          </Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  );
}
