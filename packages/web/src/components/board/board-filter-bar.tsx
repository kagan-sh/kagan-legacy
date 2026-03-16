import { ArrowUpDown, Bot, Filter, Search, Users } from 'lucide-react';
import { COLUMN_ORDER, STATUS_LABELS, SORT_LABELS, type SortOption } from '@/lib/utils/constants';
import { Button } from '@/components/ui/button';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import type { TaskStatus, WorkMode } from '@/lib/api/types';

interface BoardFilterBarProps {
  statusFilter: TaskStatus | 'ALL';
  onStatusFilterChange: (status: TaskStatus | 'ALL') => void;
  modeFilter: WorkMode | 'ALL';
  onModeFilterChange: (mode: WorkMode | 'ALL') => void;
  sort: SortOption;
  onSortChange: (sort: SortOption) => void;
  showStatusFilters?: boolean;
  query: string;
  onQueryChange: (query: string) => void;
  searchInputRef?: React.RefObject<HTMLInputElement | null>;
}

export function BoardFilterBar({
  statusFilter,
  onStatusFilterChange,
  modeFilter,
  onModeFilterChange,
  sort,
  onSortChange,
  showStatusFilters = true,
  query,
  onQueryChange,
  searchInputRef,
}: BoardFilterBarProps) {
  return (
    <div className="flex flex-wrap items-center gap-2.5 border-b border-[color:var(--border-subtle)] px-5 py-3 sm:px-6">
      {showStatusFilters ? (
        <>
          <span className="inline-flex items-center gap-1 border border-[color:var(--border-subtle)] px-3 py-2 font-code text-[11px] uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
            <Filter className="size-3.5" />
            Status
          </span>
          {(['ALL', ...COLUMN_ORDER] as const).map((value) => (
            <Button
              key={value}
              type="button"
              variant="outline"
              size="xs"
              className={`px-3 ${statusFilter === value ? 'bg-[color:var(--foreground)] text-[color:var(--background)] hover:bg-[color:var(--foreground)]/90 hover:text-[color:var(--background)]' : ''}`}
              onClick={() => onStatusFilterChange(value)}
              data-filter-pill
            >
              {value === 'ALL' ? 'All' : STATUS_LABELS[value]}
            </Button>
          ))}
          <span className="mx-1 h-5 w-px bg-[color:var(--border-subtle)]" />
        </>
      ) : null}

      {(['ALL', 'AUTO', 'PAIR'] as const).map((value) => (
        <Button
          key={value}
          type="button"
          variant="outline"
          size="xs"
          className={`px-3 ${modeFilter === value ? 'bg-[color:var(--foreground)] text-[color:var(--background)] hover:bg-[color:var(--foreground)]/90 hover:text-[color:var(--background)]' : ''}`}
          onClick={() => onModeFilterChange(value as WorkMode | 'ALL')}
          data-filter-pill
        >
          {value === 'PAIR' ? <Users className="size-3.5" /> : null}
          {value === 'AUTO' ? <Bot className="size-3.5" /> : null}
          {value === 'ALL' ? 'All modes' : value === 'AUTO' ? 'Auto' : 'Pair'}
        </Button>
      ))}

      <span className="mx-1 h-5 w-px bg-[color:var(--border-subtle)]" />

      <div className="inline-flex items-center gap-1.5">
        <ArrowUpDown className="size-3.5 text-[var(--muted-foreground)]" />
        <NativeSelect
          value={sort}
          onChange={(e) => onSortChange(e.target.value as SortOption)}
          className="h-8 w-auto border-[color:var(--border-subtle)] bg-[color:var(--surface-0)] px-3 text-xs"
          aria-label="Sort tasks"
        >
          {(Object.entries(SORT_LABELS) as [SortOption, string][]).map(([value, label]) => (
            <NativeSelectOption key={value} value={value}>{label}</NativeSelectOption>
          ))}
        </NativeSelect>
      </div>

      <div className="ml-auto inline-flex items-center gap-1.5">
        <div className="relative">
          <Search className="pointer-events-none absolute left-2.5 top-1/2 size-3.5 -translate-y-1/2 text-[var(--muted-foreground)]" />
          <input
            ref={searchInputRef}
            type="text"
            value={query}
            onChange={(e) => onQueryChange(e.target.value)}
            placeholder="Search tasks... (/)"
            className="h-8 w-44 border border-[color:var(--border-subtle)] bg-[color:var(--surface-0)] pl-8 pr-3 text-xs text-[var(--foreground)] placeholder:text-[var(--muted-foreground)] focus:border-[var(--ring)] focus:outline-none focus:ring-2 focus:ring-[var(--focus-ring)]"
            aria-label="Search tasks"
          />
        </div>
      </div>
    </div>
  );
}
