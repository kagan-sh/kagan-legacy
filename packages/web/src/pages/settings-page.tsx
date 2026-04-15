import { useRef, useState } from 'react';
import { useSetAtom } from 'jotai';
import { ArrowLeft, Bot, GitBranch, MessageSquareText, Settings, Wifi } from 'lucide-react';
import { useNavigate } from 'react-router';
import { logoutAtom } from '@/lib/atoms/auth';
import { SettingsPanel } from '@/components/settings/settings-panel';
import { ConnectionCard } from '@/components/settings/connection-card';
import { AgentPicker } from '@/components/settings/agent-picker';
import { PreflightChecks } from '@/components/settings/preflight-checks';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';

const SECTIONS = [
  { id: 'orchestration', icon: Bot, title: 'Orchestration', description: 'Agent backends, models, and execution' },
  { id: 'workflow', icon: GitBranch, title: 'Workflow', description: 'Git, reviews, and merge behaviour' },
  { id: 'instructions', icon: MessageSquareText, title: 'Instructions', description: 'Custom prompts for your agents' },
  { id: 'connection', icon: Wifi, title: 'Connection', description: 'Server status and preflight checks' },
] as const;

export function Component() {
  const logout = useSetAtom(logoutAtom);
  const navigate = useNavigate();
  const [activeSection, setActiveSection] = useState<string | null>(null);
  const settingsRef = useRef<HTMLDivElement>(null);
  const connectionRef = useRef<HTMLDivElement>(null);

  const handleLogout = () => {
    logout();
    navigate('/welcome');
  };

  const handleSectionClick = (sectionId: string) => {
    setActiveSection(sectionId);
    if (sectionId === 'connection') {
      connectionRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    } else {
      settingsRef.current?.scrollIntoView({ behavior: 'smooth', block: 'start' });
    }
  };

  return (
    <div className="mx-auto flex w-full max-w-3xl flex-col px-4 py-10 sm:px-6">
      {/* Hero header */}
      <div className="space-y-2 text-center">
        <div className="mx-auto mb-3 flex size-12 items-center justify-center text-[var(--muted-foreground)]">
          <Settings className="size-7" />
        </div>
        <h1 className="text-xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-[var(--muted-foreground)]">
          Configure how Kagan works with your codebase.
        </p>
      </div>

      {/* Action cards */}
      <div className="mt-8 space-y-2">
        {SECTIONS.map(({ id, icon: Icon, title, description }) => (
          <button
            key={id}
            type="button"
            onClick={() => handleSectionClick(id)}
            className={cn(
              'flex w-full items-center gap-4 rounded-lg border border-[color:var(--border-subtle)] px-5 py-4 text-left transition-colors hover:bg-[color:var(--surface-1)]',
              activeSection === id && 'border-[var(--primary)]/30 bg-[color:var(--surface-1)]',
            )}
          >
            <div className="flex size-9 shrink-0 items-center justify-center rounded-md bg-[color:var(--surface-2)] text-[var(--muted-foreground)]">
              <Icon className="size-4" />
            </div>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium">{title}</p>
              <p className="text-xs text-[var(--muted-foreground)]">{description}</p>
            </div>
          </button>
        ))}
      </div>

      {/* Settings content */}
      <div ref={settingsRef} className="mt-8 space-y-6">
        <div className="grid gap-5 xl:grid-cols-[minmax(0,1fr)_20rem]">
          <SettingsPanel />
          <div className="space-y-4">
            <AgentPicker />
          </div>
        </div>

        <div ref={connectionRef} className="space-y-4">
          <ConnectionCard />
          <PreflightChecks />
        </div>
      </div>

      {/* Return action */}
      <div className="mt-10 flex justify-center">
        <Button
          variant="ghost"
          size="sm"
          className="text-[var(--muted-foreground)]"
          onClick={handleLogout}
        >
          <ArrowLeft className="size-3.5" />
          Return to welcome
        </Button>
      </div>
    </div>
  );
}
