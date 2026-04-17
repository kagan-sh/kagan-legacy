import { forwardRef, type ComponentType, type SVGProps } from 'react';
import { ChevronRight } from 'lucide-react';
import { cn } from '@/lib/utils';

export interface SettingsCategoryCardProps {
  id: string;
  icon: ComponentType<SVGProps<SVGSVGElement>>;
  title: string;
  subtitle: string;
  expanded: boolean;
  onClick: () => void;
}

export const SettingsCategoryCard = forwardRef<HTMLButtonElement, SettingsCategoryCardProps>(
  function SettingsCategoryCard(
    { id, icon: Icon, title, subtitle, expanded, onClick },
    ref,
  ) {
    return (
      <button
        ref={ref}
        type="button"
        id={`settings-card-${id}`}
        aria-expanded={expanded}
        onClick={onClick}
        className={cn(
          'group flex w-full items-center gap-4 rounded-md px-4 py-3 text-left',
          'bg-[color:var(--surface-1)] hover:bg-[color:var(--surface-2)]',
          'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-[var(--ring)]',
          'transition-colors',
        )}
      >
        <span
          aria-hidden="true"
          className="flex size-9 shrink-0 items-center justify-center rounded-md bg-[color:var(--surface-2)] text-[var(--muted-foreground)] group-hover:text-[var(--foreground)]"
        >
          <Icon className="size-4" />
        </span>
        <span className="flex min-w-0 flex-1 flex-col">
          <span className="text-[15px] font-medium leading-tight">{title}</span>
          <span className="mt-0.5 text-[13px] text-[var(--muted-foreground)]">{subtitle}</span>
        </span>
        <ChevronRight
          aria-hidden="true"
          className="size-4 shrink-0 text-[var(--muted-foreground)] transition-transform group-hover:text-[var(--foreground)]"
        />
      </button>
    );
  },
);
