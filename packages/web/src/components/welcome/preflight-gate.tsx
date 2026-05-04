import { useState, useEffect, useId, useCallback, useRef } from 'react';
import { AlertTriangle, XCircle, Copy, Check } from 'lucide-react';
import { apiClient } from '@/lib/api/client';
import type { DoctorCheckResponse, DoctorReportResponse } from '@kagan/shared-api-client';
import { Alert, AlertDescription, AlertTitle } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogHeader,
  DialogTitle,
  DialogDescription,
} from '@/components/ui/dialog';
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from '@/components/ui/card';

function checkStatus(check: DoctorCheckResponse): string {
  return check.status.toLowerCase();
}

// ---------------------------------------------------------------------------
// Copy button with transient "Copied" confirmation
// ---------------------------------------------------------------------------

function CopyButton({ text, label }: { text: string; label: string }) {
  const [copied, setCopied] = useState(false);

  const handleCopy = useCallback(() => {
    if (!navigator.clipboard) return;
    void navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    });
  }, [text]);

  return (
    <button
      type="button"
      onClick={handleCopy}
      aria-label={copied ? 'Copied' : label}
      className="inline-flex items-center gap-1 rounded px-1.5 py-0.5 text-[10px] font-medium text-[var(--muted-foreground)] transition-colors hover:bg-[var(--muted)] hover:text-[var(--foreground)] focus-visible:outline-none focus-visible:ring-1 focus-visible:ring-[var(--ring)]"
    >
      {copied ? (
        <>
          <Check className="size-3 text-green-500" />
          <span className="text-green-500">Copied</span>
        </>
      ) : (
        <>
          <Copy className="size-3" />
          <span>Copy</span>
        </>
      )}
    </button>
  );
}

// ---------------------------------------------------------------------------
// Single check card (used inside the zero-ready dialog)
// ---------------------------------------------------------------------------

function CheckCard({ check }: { check: DoctorCheckResponse }) {
  const status = checkStatus(check);
  const statusColor = status === 'fail'
    ? 'border-l-[var(--destructive)]'
    : 'border-l-amber-500';

  return (
    <Card className={`border-l-2 ${statusColor} gap-3 py-4`}>
      <CardHeader className="px-4 pb-0 pt-0">
        <div className="flex items-start justify-between gap-2">
          <div className="min-w-0 flex-1">
            <CardTitle className="text-sm">{check.name}</CardTitle>
            <CardDescription className="mt-0.5 text-xs">{check.message}</CardDescription>
          </div>
          <span className={`shrink-0 font-code text-[10px] font-semibold uppercase tracking-wider ${status === 'fail' ? 'text-[var(--destructive)]' : 'text-amber-500'}`}>
            {check.status}
          </span>
        </div>
      </CardHeader>
      {check.fix_hint && (
        <CardContent className="px-4 pb-0">
          <div className="flex items-start justify-between gap-2 rounded bg-[color:var(--surface-0)] p-2">
            <code className="min-w-0 flex-1 break-all font-code text-[11px] text-[var(--foreground)]">
              {check.fix_hint}
            </code>
            <CopyButton text={check.fix_hint} label={`Copy fix hint for ${check.name}`} />
          </div>
        </CardContent>
      )}
    </Card>
  );
}

// ---------------------------------------------------------------------------
// Zero-ready dialog (FAIL state) — non-dismissible, no Escape
// ---------------------------------------------------------------------------

function ZeroReadyDialog({
  checks,
  dialogTitleId,
  dialogDescId,
  firstCopyRef,
}: {
  checks: DoctorCheckResponse[];
  dialogTitleId: string;
  dialogDescId: string;
  firstCopyRef: React.RefObject<HTMLButtonElement | null>;
}) {
  // Radix Dialog fires onOpenChange(false) for Escape and overlay clicks.
  // We intercept with onEscapeKeyDown and onPointerDownOutside to suppress.
  return (
    <Dialog open modal>
      <DialogContent
        showCloseButton={false}
        overlayClassName="cursor-not-allowed"
        className="motion-safe:data-[state=open]:animate-in motion-safe:data-[state=open]:fade-in-0 motion-safe:data-[state=open]:zoom-in-95 motion-safe:data-[state=closed]:animate-out motion-safe:data-[state=closed]:fade-out-0 motion-safe:data-[state=closed]:zoom-out-95 max-h-[80vh] max-w-lg overflow-y-auto"
        aria-modal="true"
        aria-labelledby={dialogTitleId}
        aria-describedby={dialogDescId}
        onEscapeKeyDown={(e) => e.preventDefault()}
        onPointerDownOutside={(e) => e.preventDefault()}
        onInteractOutside={(e) => e.preventDefault()}
      >
        <DialogHeader>
          <div className="flex items-center gap-2">
            <XCircle className="size-5 text-[var(--destructive)]" aria-hidden="true" />
            <DialogTitle id={dialogTitleId} className="text-[var(--destructive)]">
              Setup required
            </DialogTitle>
          </div>
          <DialogDescription id={dialogDescId}>
            Kagan found configuration issues that must be resolved before you can use the dashboard.
            Fix the items below and restart the server.
          </DialogDescription>
        </DialogHeader>

        <div className="space-y-3">
          {checks.map((check) => (
            <div key={check.name} ref={null}>
              <CheckCard check={check} />
            </div>
          ))}
        </div>

        {/* Invisible sentinel so we can focus the first copy button */}
        <div className="sr-only">
          <button
            type="button"
            ref={firstCopyRef as React.RefObject<HTMLButtonElement>}
            tabIndex={-1}
            aria-hidden="true"
          />
        </div>
      </DialogContent>
    </Dialog>
  );
}

// ---------------------------------------------------------------------------
// Degraded banner (WARN-only state) — dismissible for the session
// ---------------------------------------------------------------------------

function DegradedBanner({
  checks,
  onDismiss,
}: {
  checks: DoctorCheckResponse[];
  onDismiss: () => void;
}) {
  const warnNames = checks.filter((c) => checkStatus(c) === 'warn').map((c) => c.name);

  return (
    <Alert className="mb-6 border-amber-500/50 bg-amber-500/10 text-[var(--foreground)]">
      <AlertTriangle className="size-4 text-amber-500" aria-hidden="true" />
      <AlertTitle className="text-amber-600 dark:text-amber-400">
        Degraded configuration
      </AlertTitle>
      <AlertDescription>
        <p className="mb-2 text-xs text-[var(--muted-foreground)]">
          Some optional checks failed. Kagan will work but with reduced functionality.
        </p>
        <ul className="mb-3 space-y-0.5">
          {warnNames.map((name) => (
            <li key={name} className="font-code text-xs">
              {name}
            </li>
          ))}
        </ul>
        <Button
          variant="outline"
          size="sm"
          onClick={onDismiss}
          className="border-amber-500/50 text-xs hover:bg-amber-500/10"
        >
          Dismiss
        </Button>
      </AlertDescription>
    </Alert>
  );
}

// ---------------------------------------------------------------------------
// PreflightGate — top-level orchestrator rendered on /welcome mount
// ---------------------------------------------------------------------------

type PreflightState =
  | { kind: 'idle' }
  | { kind: 'loading' }
  | { kind: 'all-green' }
  | { kind: 'degraded'; checks: DoctorCheckResponse[] }
  | { kind: 'zero-ready'; checks: DoctorCheckResponse[] }
  | { kind: 'error' };

export function PreflightGate() {
  const [state, setState] = useState<PreflightState>({ kind: 'idle' });
  const [bannerDismissed, setBannerDismissed] = useState(false);

  // Fired once on mount only
  useEffect(() => {
    let cancelled = false;
    setState({ kind: 'loading' });

    void apiClient
      .getDoctorReport()
      .then((report: DoctorReportResponse) => {
        if (cancelled) return;

        if (report.ok) {
          setState({ kind: 'all-green' });
          return;
        }

        const failing = report.checks.filter((c) => {
          const status = checkStatus(c);
          return status === 'fail' || status === 'warn';
        });
        const hasFail = report.fail_count > 0;

        if (hasFail) {
          setState({ kind: 'zero-ready', checks: failing });
        } else {
          setState({ kind: 'degraded', checks: failing });
        }
      })
      .catch(() => {
        if (!cancelled) setState({ kind: 'error' });
      });

    return () => {
      cancelled = true;
    };
  }, []);

  const dialogTitleId = useId();
  const dialogDescId = useId();

  // Focus management: move focus to the first copy button inside the dialog
  const firstCopyRef = useRef<HTMLButtonElement | null>(null);
  useEffect(() => {
    if (state.kind !== 'zero-ready') return;
    // Radix focuses the content element after open animation; nudge to first copy button
    const raf = requestAnimationFrame(() => {
      if (firstCopyRef.current) firstCopyRef.current.focus();
    });
    return () => cancelAnimationFrame(raf);
  }, [state.kind]);

  if (state.kind === 'zero-ready') {
    return (
      <ZeroReadyDialog
        checks={state.checks}
        dialogTitleId={dialogTitleId}
        dialogDescId={dialogDescId}
        firstCopyRef={firstCopyRef}
      />
    );
  }

  if (state.kind === 'degraded' && !bannerDismissed) {
    return <DegradedBanner checks={state.checks} onDismiss={() => setBannerDismissed(true)} />;
  }

  // all-green, loading, error, dismissed degraded: render nothing
  return null;
}
