import { useSetAtom } from 'jotai';
import { ArrowLeft, Settings } from 'lucide-react';
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
    <div className="mx-auto flex w-full max-w-2xl flex-col px-4 py-10 sm:px-6">
      {/* Hero */}
      <div className="space-y-2 text-center">
        <div className="mx-auto mb-3 flex size-12 items-center justify-center text-[var(--muted-foreground)]">
          <Settings className="size-7" />
        </div>
        <h1 className="text-xl font-semibold tracking-tight">Settings</h1>
        <p className="text-sm text-[var(--muted-foreground)]">
          Configure how Kagan works with your codebase.
        </p>
      </div>

      {/* All sections stacked in one column */}
      <div className="mt-8 space-y-4">
        <SettingsPanel />
        <AgentPicker />
        <ConnectionCard />
        <PreflightChecks />
      </div>

      {/* Return */}
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
