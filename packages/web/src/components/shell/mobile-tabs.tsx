import { Link, useLocation } from 'react-router';
import { Kanban, MessagesSquare, Settings } from 'lucide-react';
import { cn } from '@/lib/utils';

type TabId = 'workspace' | 'kanban' | 'settings';

interface Tab {
  id: TabId;
  to: string;
  icon: React.FC<React.SVGProps<SVGSVGElement>>;
  label: string;
}

const TABS: Tab[] = [
  { id: 'workspace', to: '/chat', icon: MessagesSquare, label: 'Workspace' },
  { id: 'kanban', to: '/board', icon: Kanban, label: 'Kanban' },
  { id: 'settings', to: '/settings', icon: Settings, label: 'Settings' },
];

function activeTabFor(pathname: string): TabId {
  if (pathname.startsWith('/board') || pathname.startsWith('/task')) return 'kanban';
  if (pathname.startsWith('/settings')) return 'settings';
  return 'workspace';
}

export function MobileTabs() {
  const location = useLocation();
  const active = activeTabFor(location.pathname);

  return (
    <nav
      aria-label="Mobile tabs"
      className="fixed inset-x-0 bottom-0 z-40 grid grid-cols-3 border-t border-[var(--border)] bg-[var(--surface-1)] md:hidden"
      style={{ height: 56, paddingBottom: 'env(safe-area-inset-bottom)' }}
    >
      {TABS.map(({ id, to, icon: Icon, label }) => {
        const isActive = active === id;
        return (
          <Link
            key={id}
            to={to}
            aria-current={isActive ? 'page' : undefined}
            data-active={isActive ? 'true' : undefined}
            className={cn(
              'relative flex min-h-[44px] flex-col items-center justify-center gap-1 px-2 py-2 font-ui text-[11px] font-medium transition-colors',
              isActive
                ? 'text-[var(--foreground)]'
                : 'text-[var(--muted-foreground)] hover:text-[var(--fg-2)]',
            )}
          >
            {isActive && (
              <span
                aria-hidden
                className="absolute inset-x-0 top-0 h-0.5 bg-[var(--primary)]"
              />
            )}
            <Icon
              className="size-[18px]"
              strokeWidth={1.75}
            />
            <span>{label}</span>
          </Link>
        );
      })}
    </nav>
  );
}
