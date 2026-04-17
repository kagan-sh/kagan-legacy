import { ArrowRight } from 'lucide-react';
import { describeIntent, type ClassifiedIntent } from '@/lib/intent/classify-intent';
import { cn } from '@/lib/utils';

interface IntentPreviewProps {
  intent: ClassifiedIntent;
  /** The raw input — used as a fallback preview when the classifier is unsure. */
  rawInput: string;
  /** Render nothing when the user hasn't typed enough. */
  visible: boolean;
}

function confidenceTone(confidence: number): string {
  if (confidence >= 0.7) return 'bg-[color:var(--surface-2)] text-[var(--foreground)]';
  if (confidence >= 0.4) return 'bg-[color:var(--surface-2)] text-[var(--muted-foreground)]';
  return 'bg-transparent text-[var(--muted-foreground)]';
}

/**
 * Inline chip that previews where Enter will take the user.
 *
 * Renders an invisible placeholder when `visible` is false so the input
 * above doesn't visibly jump when the preview first appears.
 */
export function IntentPreview({ intent, rawInput, visible }: IntentPreviewProps) {
  if (!visible) {
    return <div aria-hidden className="h-7" />;
  }

  const description = describeIntent(intent, rawInput);

  return (
    <div
      id="home-intent-preview"
      className={cn(
        'flex h-7 items-center gap-1.5 self-start px-2 font-code text-[11px] uppercase tracking-[0.14em]',
        confidenceTone(intent.confidence),
      )}
    >
      <ArrowRight className="size-3" aria-hidden />
      <span className="truncate">{description}</span>
    </div>
  );
}
