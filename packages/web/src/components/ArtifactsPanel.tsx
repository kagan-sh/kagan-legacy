import { useState, useEffect } from 'react';
import { useAtomValue } from 'jotai';
import { X } from 'lucide-react';
import { artifactsAtom, type Artifact } from '@/lib/atoms/artifacts';
import { MarkdownContent } from '@/components/shared/markdown-content';

// ---------------------------------------------------------------------------
// Individual artifact view — sandboxed iframes for HTML/SVG, prose for MD
// ---------------------------------------------------------------------------

// TODO(artifacts/pdf-docx-xlsx): PDF, DOCX, and XLSX deferred to a follow-up.

function ArtifactView({ artifact }: { artifact: Artifact }) {
  if (artifact.type === 'html') {
    return (
      <iframe
        // Most-restrictive sandbox: no scripts, no same-origin access.
        sandbox=""
        srcDoc={artifact.content}
        title={artifact.title ?? `Artifact ${artifact.id}`}
        className="h-full w-full border-0"
      />
    );
  }

  if (artifact.type === 'svg') {
    // Wrap the raw SVG in a minimal HTML document so the iframe can render it.
    const doc = `<!doctype html><html><body style="margin:0;display:flex;align-items:center;justify-content:center;height:100vh;">${artifact.content}</body></html>`;
    return (
      <iframe
        sandbox=""
        srcDoc={doc}
        title={artifact.title ?? `Artifact ${artifact.id}`}
        className="h-full w-full border-0"
      />
    );
  }

  // markdown
  return (
    <div className="overflow-y-auto p-4">
      <MarkdownContent content={artifact.content} />
    </div>
  );
}

// ---------------------------------------------------------------------------
// Panel header tab bar
// ---------------------------------------------------------------------------

function TabBar({
  artifacts,
  activeId,
  onSelect,
  onClose,
}: {
  artifacts: Artifact[];
  activeId: string | null;
  onSelect: (id: string) => void;
  onClose: () => void;
}) {
  return (
    <div className="flex items-center justify-between border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-1)]">
      <div className="flex min-w-0 overflow-x-auto">
        {artifacts.map((a) => (
          <button
            key={a.id}
            type="button"
            onClick={() => onSelect(a.id)}
            className={
              a.id === activeId
                ? 'shrink-0 border-b-2 border-[var(--primary)] px-3 py-2 font-code text-xs text-[var(--foreground)]'
                : 'shrink-0 border-b-2 border-transparent px-3 py-2 font-code text-xs text-[var(--muted-foreground)] hover:text-[var(--foreground)]'
            }
          >
            {a.title ?? a.type}
          </button>
        ))}
      </div>
      <button
        type="button"
        onClick={onClose}
        aria-label="Close artifacts panel"
        className="shrink-0 p-2 text-[var(--muted-foreground)] hover:text-[var(--foreground)]"
      >
        <X className="size-3.5" />
      </button>
    </div>
  );
}

// ---------------------------------------------------------------------------
// ArtifactsPanel
//
// Collapsible side drawer — rendered when artifactsAtom is non-empty.
// Consumers should place this beside the chat area and let it expand
// automatically when artifacts appear (via open prop).
// ---------------------------------------------------------------------------

interface ArtifactsPanelProps {
  open: boolean;
  onClose: () => void;
}

export function ArtifactsPanel({ open, onClose }: ArtifactsPanelProps) {
  const artifacts = useAtomValue(artifactsAtom);
  const [activeId, setActiveId] = useState<string | null>(null);

  // Auto-focus the newest artifact when one is added
  useEffect(() => {
    if (artifacts.length > 0) {
      const last = artifacts[artifacts.length - 1];
      if (last) setActiveId(last.id);
    }
  }, [artifacts]);

  if (!open || artifacts.length === 0) return null;

  const activeArtifact = artifacts.find((a) => a.id === activeId) ?? artifacts[artifacts.length - 1];

  return (
    <div className="flex h-full w-full flex-col border-l border-[color:var(--border-subtle)] bg-[color:var(--background)]">
      <TabBar
        artifacts={artifacts}
        activeId={activeArtifact?.id ?? null}
        onSelect={setActiveId}
        onClose={onClose}
      />
      <div className="min-h-0 flex-1 overflow-hidden">
        {activeArtifact ? (
          <ArtifactView artifact={activeArtifact} />
        ) : null}
      </div>
    </div>
  );
}
