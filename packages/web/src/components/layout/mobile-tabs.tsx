import { NavLink } from 'react-router';
import { useSetAtom } from 'jotai';
import { HelpCircle, LayoutDashboard, MessageSquare, MessageSquareText, Settings } from 'lucide-react';
import { cn } from '@/lib/utils';
import { helpOverlayOpenAtom, sessionPickerOpenAtom } from '@/lib/atoms/ui';
import { Button } from '@/components/ui/button';

const TABS = [
  { to: '/board', icon: LayoutDashboard, label: 'Board' },
  { to: '/workspace', icon: MessageSquareText, label: 'Workspace' },
  { to: '/settings', icon: Settings, label: 'Settings' },
] as const;

export function MobileTabs() {
  const setSessionPickerOpen = useSetAtom(sessionPickerOpenAtom);
  const setHelpOverlayOpen = useSetAtom(helpOverlayOpenAtom);

  return (
    <nav className="glass-surface fixed inset-x-0 bottom-0 z-40 border-t border-[color:var(--border-subtle)] border-x-0 border-b-0 px-2 pb-[calc(env(safe-area-inset-bottom)+0.45rem)] pt-2 lg:hidden">
      <div className="mx-auto grid max-w-md grid-cols-5 gap-1">
        {TABS.map(({ to, icon: Icon, label }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              cn(
                'flex min-h-14 flex-col items-center justify-center gap-1 px-1 py-2.5 text-[11px] font-medium transition-colors',
                isActive
                  ? 'bg-[color:var(--surface-2)] text-[var(--foreground)]'
                  : 'text-[var(--muted-foreground)]',
              )
            }
          >
            <Icon className="size-4" />
            <span>{label}</span>
          </NavLink>
        ))}
        <Button
          type="button"
          variant="ghost"
          onClick={() => {
            setHelpOverlayOpen(false);
            setSessionPickerOpen(true);
          }}
          className="min-h-14 flex-col gap-1 rounded-none px-1 py-2.5 text-[11px] font-medium text-[var(--muted-foreground)]"
          aria-label="Open Session Switcher"
        >
          <MessageSquare className="size-4" />
          <span>Sessions</span>
        </Button>
        <Button
          type="button"
          variant="ghost"
          onClick={() => {
            setSessionPickerOpen(false);
            setHelpOverlayOpen(true);
          }}
          className="min-h-14 flex-col gap-1 rounded-none px-1 py-2.5 text-[11px] font-medium text-[var(--muted-foreground)]"
          aria-label="Open help"
        >
          <HelpCircle className="size-4" />
          <span>Help</span>
        </Button>
      </div>
    </nav>
  );
}
