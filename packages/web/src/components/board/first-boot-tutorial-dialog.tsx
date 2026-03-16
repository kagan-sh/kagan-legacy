import { useMemo, useState } from 'react';
import { Bot, Sparkles, Users } from 'lucide-react';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';
import { Kbd, KbdGroup } from '@/components/ui/kbd';

interface FirstBootTutorialDialogProps {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  onStartAutoFlow: () => void;
  onStartPairFlow: () => void;
  onOpenHelp: () => void;
}

const STEPS = [
  {
    title: 'Welcome to the board',
    description: 'You can run agents in autonomous or collaborative mode from the same task workflow.',
  },
  {
    title: 'PAIR flow',
    description: 'PAIR mode is best when you want to guide strategy, clarify intent, and iterate quickly.',
  },
  {
    title: 'AUTO flow',
    description: 'AUTO mode is best when scope is clear and you want fast execution throughput.',
  },
] as const;

export function FirstBootTutorialDialog({
  open,
  onOpenChange,
  onStartAutoFlow,
  onStartPairFlow,
  onOpenHelp,
}: FirstBootTutorialDialogProps) {
  const [stepIndex, setStepIndex] = useState(0);

  const step = STEPS[stepIndex] ?? STEPS[0];
  const isFirst = stepIndex === 0;
  const isLast = stepIndex === STEPS.length - 1;

  const progressLabel = useMemo(
    () => `${stepIndex + 1} / ${STEPS.length}`,
    [stepIndex],
  );

  return (
    <Dialog
      open={open}
      onOpenChange={(nextOpen) => {
        onOpenChange(nextOpen);
        if (!nextOpen) {
          setStepIndex(0);
        }
      }}
    >
      <DialogContent className="max-w-2xl p-0">
        <DialogHeader className="border-b border-[color:var(--border-subtle)] px-5 pt-5 pb-4">
          <DialogTitle className="flex items-center justify-between gap-3 text-base">
            <span className="inline-flex items-center gap-2">
              <Sparkles className="size-4" />
              Guided Tutorial
            </span>
            <span className="font-code text-[10px] uppercase tracking-[0.16em] text-[var(--muted-foreground)]">
              {progressLabel}
            </span>
          </DialogTitle>
          <DialogDescription>{step.description}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4 px-5 py-5">
          <Card>
            <CardHeader className="gap-1">
              <CardTitle className="text-sm">{step.title}</CardTitle>
              <CardDescription>Follow this flow to learn the board in real usage, not static docs.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              {stepIndex === 0 ? (
                <div className="space-y-2 text-sm text-[var(--muted-foreground)]">
                  <p>Start with PAIR when requirements are fluid. Use AUTO when acceptance criteria are stable.</p>
                  <p>Everything remains reviewable in task detail and diff views before merge.</p>
                  <div className="flex flex-wrap items-center gap-2 pt-1">
                    <KbdGroup>
                      <Kbd>Cmd/Ctrl</Kbd>
                      <Kbd>Shift</Kbd>
                      <Kbd>K</Kbd>
                    </KbdGroup>
                    <span>Session Switcher</span>
                    <KbdGroup>
                      <Kbd>?</Kbd>
                      <Kbd>F1</Kbd>
                    </KbdGroup>
                    <span>Help & Shortcuts</span>
                  </div>
                </div>
              ) : null}

              {stepIndex === 1 ? (
                <div className="space-y-3">
                  <p className="text-sm text-[var(--muted-foreground)]">
                    Create a PAIR task now. This opens the create dialog preconfigured for collaborative execution.
                  </p>
                  <Button onClick={onStartPairFlow} className="w-full sm:w-auto">
                    <Users className="size-4" />
                    Start PAIR flow
                  </Button>
                </div>
              ) : null}

              {stepIndex === 2 ? (
                <div className="space-y-3">
                  <p className="text-sm text-[var(--muted-foreground)]">
                    Create an AUTO task now. This opens the create dialog preconfigured for autonomous execution.
                  </p>
                  <Button onClick={onStartAutoFlow} className="w-full sm:w-auto">
                    <Bot className="size-4" />
                    Start AUTO flow
                  </Button>
                </div>
              ) : null}
            </CardContent>
          </Card>

          <div className="flex flex-col-reverse gap-2 sm:flex-row sm:items-center sm:justify-between">
            <Button
              variant="ghost"
              onClick={onOpenHelp}
            >
              Open full help
            </Button>
            <div className="flex gap-2 sm:justify-end">
              <Button
                variant="outline"
                onClick={() => setStepIndex((prev) => Math.max(0, prev - 1))}
                disabled={isFirst}
              >
                Back
              </Button>
              {isLast ? (
                <Button onClick={() => onOpenChange(false)}>Finish</Button>
              ) : (
                <Button onClick={() => setStepIndex((prev) => Math.min(STEPS.length - 1, prev + 1))}>
                  Next
                </Button>
              )}
            </div>
          </div>
        </div>
      </DialogContent>
    </Dialog>
  );
}
