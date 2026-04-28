import { NavLink } from 'react-router';
import { Home, LayoutDashboard, MessageSquareText, Settings } from 'lucide-react';
import { cn } from '@/lib/utils';

// Analytics is intentionally excluded from primary nav.
// Access it via: command palette (Cmd+K → "Go to Analytics") or /settings#advanced.
const ITEMS = [
  { to: '/home', label: 'Home', icon: Home },
  { to: '/board', label: 'Board', icon: LayoutDashboard },
  { to: '/workspace', label: 'Workspace', icon: MessageSquareText },
  { to: '/settings', label: 'Settings', icon: Settings },
] as const;

export function ActivityBar() {
  return (
    <aside className="hidden w-16 shrink-0 bg-[color:var(--surface-0)] lg:flex lg:flex-col">
      <div className="flex h-16 items-center justify-center">
        <NavLink
          to="/"
          aria-label="Kagan home"
          className="inline-flex items-center gap-1 px-2 py-1 text-[var(--foreground)] transition-[color,transform] duration-[var(--motion-fast)] hover:text-[var(--primary)] active:scale-95"
        >
          <span className="font-code text-[12px] tracking-[0.08em]">ᘚᘛ</span>
        </NavLink>
      </div>

      <nav aria-label="Main navigation" className="flex flex-1 flex-col items-center gap-2 px-2 py-5">
        {ITEMS.map(({ to, label, icon: Icon }) => (
          <NavLink
            key={to}
            to={to}
            aria-label={label}
            className={({ isActive }) =>
              cn(
                'group relative p-2 text-[var(--muted-foreground)] transition-[background-color,color] duration-[var(--motion-fast)] hover:bg-[color:var(--surface-2)] hover:text-[var(--foreground)]',
                isActive && 'bg-[color:var(--surface-2)] text-[var(--foreground)]',
              )
            }
          >
            {({ isActive }) => (
              <div className="relative flex items-center justify-center">
                <div className={cn(
                  'flex size-8 items-center justify-center ',
                  isActive && 'bg-[color:var(--surface-3)]',
                )}>
                  <Icon className="size-4" />
                </div>
                <span className="pointer-events-none absolute left-[calc(100%+0.6rem)] top-1/2 z-20 -translate-y-1/2 bg-[color:var(--surface-2)] px-2 py-1 font-code text-[11px] uppercase tracking-[0.16em] text-[var(--foreground)] opacity-0 shadow-[var(--ambient-shadow)] transition-opacity duration-[var(--motion-fast)] group-hover:opacity-100 group-focus-visible:opacity-100">
                  {label}
                </span>
                <span className="sr-only">{label}</span>
              </div>
            )}
          </NavLink>
        ))}
      </nav>
    </aside>
  );
}
