import { useSetAtom } from 'jotai';
import { ArrowLeft } from 'lucide-react';
import { useNavigate } from 'react-router';
import { logoutAtom } from '@/lib/atoms/auth';
import { SettingsPanel } from '@/components/settings/settings-panel';
import { ConnectionCard } from '@/components/settings/connection-card';
import { AgentPicker } from '@/components/settings/agent-picker';
import { PreflightChecks } from '@/components/settings/preflight-checks';
import { Button } from '@/components/ui/button';

export function Component() {
  const logout = useSetAtom(logoutAtom);
  const navigate = useNavigate();

  const handleLogout = () => {
    logout();
    navigate('/welcome');
  };

  return (
    <div className="mx-auto flex w-full max-w-[1680px] flex-col px-4 py-3 sm:px-6">
      <div className="flex items-center gap-3 border-b border-[color:var(--border-subtle)] pb-3">
        <h1 className="text-sm font-semibold">Preferences</h1>
        <span className="h-4 w-px bg-[color:var(--border-subtle)]" />
        <span className="text-xs text-[var(--muted-foreground)]">Runtime, identity &amp; orchestration defaults</span>
        <div className="ml-auto">
          <Button
            variant="outline"
            size="sm"
            className="border-[var(--destructive)] text-[var(--destructive)] hover:bg-[var(--destructive)]/10 hover:text-[var(--destructive)]"
            onClick={handleLogout}
          >
            <ArrowLeft className="size-3.5" />
            Return to welcome
          </Button>
        </div>
      </div>

      <div className="mt-3 grid gap-5 xl:grid-cols-[minmax(0,1fr)_22rem]">
        <SettingsPanel />
        <div className="space-y-4">
          <AgentPicker />
          <ConnectionCard />
          <PreflightChecks />
        </div>
      </div>
    </div>
  );
}
