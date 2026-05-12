import { useEffect, useState } from 'react';
import { useNavigate } from 'react-router';
import { useAtom } from 'jotai';
import { toast } from 'sonner';
import { newSessionModalOpenAtom } from '@/lib/atoms/shell';
import { apiClient } from '@/lib/api/client';
import { cn } from '@/lib/utils';

type SessionKind = 'orchestrator' | 'general';

export function NewSessionDialog() {
  const [open, setOpen] = useAtom(newSessionModalOpenAtom);
  const navigate = useNavigate();
  const [kind, setKind] = useState<SessionKind>('orchestrator');
  const [agents, setAgents] = useState<string[]>([]);
  const [agent, setAgent] = useState('');
  const [title, setTitle] = useState('');
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!open) return;
    setKind('orchestrator');
    setTitle('');
    setSubmitting(false);
    apiClient
      .getChatAgents()
      .then((res) => {
        const names = res.backends.filter((b) => b.available).map((b) => b.name);
        setAgents(names);
        const next = names.includes(res.default) ? res.default : names[0];
        if (next) setAgent(next);
      })
      .catch(() => {});
  }, [open]);

  async function submit() {
    if (submitting) return;
    setSubmitting(true);
    try {
      const session = await apiClient.createSession({
        type: kind,
        backend: agent || null,
        title: title.trim() || null,
      });
      toast.success(`Created ${session.title || session.id.slice(0, 8)}`);
      setOpen(false);
      navigate(`/chat/${session.id}`);
    } catch (err) {
      toast.error(err instanceof Error ? err.message : 'Failed to create session');
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) return null;

  return (
    <div
      role="dialog"
      aria-modal="true"
      aria-label="New session"
      className="fixed inset-0 z-[200] flex items-center justify-center backdrop-blur-[3px]"
      style={{ background: 'rgba(0,0,0,0.6)' }}
      onClick={(e) => {
        if (e.target === e.currentTarget) setOpen(false);
      }}
    >
      <div className="w-[460px] max-w-[90%] rounded-[10px] border border-[var(--border)] bg-[var(--card)] px-5 py-4.5 shadow-[0_20px_60px_-10px_rgba(0,0,0,0.7)]">
        <h2 className="mb-1 font-ui text-[14px] font-semibold text-[var(--foreground)]">New session</h2>
        <div className="mb-4 font-code text-[11px] tracking-[0.04em] text-[var(--fg-dim)]">
          Standalone chat not tied to a specific task.
        </div>

        <Label>Type</Label>
        <div className="mb-4 grid grid-cols-2 gap-2">
          <KindOption
            sel={kind === 'orchestrator'}
            onClick={() => setKind('orchestrator')}
            icon="◈"
            label="Orchestrator"
            desc="Direct agents, create and assign tasks"
          />
          <KindOption
            sel={kind === 'general'}
            onClick={() => setKind('general')}
            icon="○"
            label="General"
            desc="Freeform chat — planning, exploration, Q&A"
          />
        </div>

        <Label>Agent</Label>
        <select
          value={agent}
          onChange={(e) => setAgent(e.target.value)}
          className="mb-3 w-full rounded-md border border-[var(--border)] bg-[var(--surface-1)] px-2.5 py-2 font-ui text-[13px] text-[var(--foreground)] outline-none focus:border-[var(--primary)]"
        >
          {agents.map((a) => (
            <option key={a} value={a}>
              {a}
            </option>
          ))}
        </select>

        <Label>
          Name <span className="font-normal opacity-50">(optional)</span>
        </Label>
        <input
          type="text"
          value={title}
          onChange={(e) => setTitle(e.target.value)}
          placeholder="e.g. MCP strategy discussion"
          className="mb-4 w-full rounded-md border border-[var(--border)] bg-[var(--surface-1)] px-2.5 py-2 font-ui text-[13px] text-[var(--foreground)] outline-none focus:border-[var(--primary)]"
        />

        <div className="mt-4.5 flex justify-end gap-2">
          <button
            type="button"
            onClick={() => setOpen(false)}
            className="cursor-pointer rounded-md border border-[var(--border)] bg-[var(--surface-1)] px-3.5 py-1.5 font-ui text-[12.5px] font-medium text-[var(--fg-2)] hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]"
          >
            Cancel
          </button>
          <button
            type="button"
            disabled={submitting}
            onClick={submit}
            className="cursor-pointer rounded-md border border-[var(--primary)] bg-[var(--primary)] px-3.5 py-1.5 font-ui text-[12.5px] font-medium text-[#0b0a09] shadow-[0_0_18px_-4px_rgba(212,168,75,0.5)] hover:bg-[var(--primary-bright)] disabled:cursor-not-allowed disabled:opacity-60"
          >
            Start session
          </button>
        </div>
      </div>
    </div>
  );
}

function Label({ children }: { children: React.ReactNode }) {
  return (
    <label className="mb-1.5 mt-3 block font-code text-[10px] font-semibold uppercase tracking-[0.22em] text-[var(--fg-dim)]">
      {children}
    </label>
  );
}

interface KindProps {
  sel: boolean;
  onClick: () => void;
  icon: string;
  label: string;
  desc: string;
}

function KindOption({ sel, onClick, icon, label, desc }: KindProps) {
  return (
    <button
      type="button"
      onClick={onClick}
      data-sel={sel ? 'true' : 'false'}
      className={cn(
        'flex w-full cursor-pointer flex-col gap-1 rounded-md border bg-transparent px-3 py-3 text-left font-ui transition-colors',
        sel ? 'border-[var(--primary)] bg-[rgba(212,168,75,0.06)]' : 'border-[var(--border)] hover:bg-[var(--surface-2)]',
      )}
    >
      <span className="font-code text-[18px] text-[var(--primary)]">{icon}</span>
      <span className="text-[13px] font-medium text-[var(--foreground)]">{label}</span>
      <span className="text-[11.5px] leading-snug text-[var(--muted-foreground)]">{desc}</span>
    </button>
  );
}
