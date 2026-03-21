import type { ReactNode } from 'react';
import { cn } from '@/lib/utils';

interface WorkspaceHeaderProps {
  title: ReactNode;
  description?: ReactNode;
  actions?: ReactNode;
  className?: string;
}

export function WorkspaceHeader({
  title,
  description,
  actions,
  className,
}: WorkspaceHeaderProps) {
  return (
    <header
      className={cn(
        'flex items-center justify-between gap-4 px-5 py-3 sm:px-6',
        className,
      )}
    >
      <div className="min-w-0 flex-1">
        <div className="min-w-0 line-clamp-1">{title}</div>
        {description ? (
          <p className="mt-0.5 line-clamp-1 max-w-3xl text-[13px] leading-5 text-[var(--muted-foreground)]">
            {description}
          </p>
        ) : null}
      </div>

      {actions ? <div className="flex shrink-0 flex-wrap items-center gap-2">{actions}</div> : null}
    </header>
  );
}

export function Panel({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <section className={cn(' border border-border/50 bg-card', className)}>
      {children}
    </section>
  );
}

interface InspectorSectionProps {
  title: string;
  description?: string;
  action?: ReactNode;
  className?: string;
  children: ReactNode;
}

export function InspectorSection({
  title,
  description,
  action,
  className,
  children,
}: InspectorSectionProps) {
  return (
    <section
      className={cn(
        ' border border-border/50 bg-[color:var(--surface-1)] p-4',
        className,
      )}
    >
      <div className="mb-3 flex items-start justify-between gap-3">
        <div className="space-y-1">
          <h3 className="text-sm font-semibold">{title}</h3>
          {description ? (
            <p className="text-xs leading-5 text-[var(--muted-foreground)]">{description}</p>
          ) : null}
        </div>
        {action}
      </div>
      {children}
    </section>
  );
}

export function StickyActionBar({
  className,
  children,
}: {
  className?: string;
  children: ReactNode;
}) {
  return (
    <div
      className={cn(
        'sticky top-0 z-20 flex flex-wrap items-center gap-2 border-b border-[color:var(--border-subtle)] bg-[color:var(--surface-overlay)] px-5 py-3 backdrop-blur-xl sm:px-6',
        className,
      )}
    >
      {children}
    </div>
  );
}

interface ActionEmptyStateProps {
  title: string;
  description: string;
  icon?: ReactNode;
  action?: ReactNode;
  className?: string;
}

export function ActionEmptyState({
  title,
  description,
  icon,
  action,
  className,
}: ActionEmptyStateProps) {
  return (
    <div
      className={cn(
        'flex min-h-[10rem] flex-col items-center justify-center gap-2 bg-[color:var(--surface-1)]/50 px-4 py-6 text-center',
        className,
      )}
    >
      {icon ? (
        <div className="flex size-10 items-center justify-center bg-[color:var(--surface-2)] text-[var(--muted-foreground)] shadow-[var(--soft-shadow)]">
          {icon}
        </div>
      ) : null}
      <div className="space-y-1">
        <h3 className="line-clamp-1 text-base font-semibold">{title}</h3>
        <p className="line-clamp-2 max-w-md text-sm leading-5 text-[var(--muted-foreground)]">{description}</p>
      </div>
      {action}
    </div>
  );
}
