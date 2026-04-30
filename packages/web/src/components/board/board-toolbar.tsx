import type { RefObject } from 'react';
import {
  LayoutGrid,
  ListTodo,
  Plus,
  Download,
  Radar,
  Search,
} from 'lucide-react';
import { COLUMN_ORDER, STATUS_LABELS, SORT_LABELS, type SortOption } from '@/lib/utils/constants';
import { NativeSelect, NativeSelectOption } from '@/components/ui/native-select';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { ToggleGroup, ToggleGroupItem } from '@/components/ui/toggle-group';
import type { TaskStatus } from '@/lib/api/types';

type StatusFilterValue = TaskStatus | 'ALL';

interface BoardMetrics {
  running: number;
  readyForReview: number;
}

interface BoardToolbarProps {
  query: string;
  setQuery: (query: string) => void;
  statusFilter: StatusFilterValue;
  setStatusFilter: (filter: StatusFilterValue) => void;
  sort: SortOption;
  setSort: (sort: SortOption) => void;
  view: 'kanban' | 'backlog';
  setView: (view: 'kanban' | 'backlog') => void;
  boardMetrics: BoardMetrics;
  onCreateTask: () => void;
  onImportGitHub?: () => void;
  searchInputRef: RefObject<HTMLInputElement | null>;
}

export function BoardToolbar({
  query,
  setQuery,
  statusFilter,
  setStatusFilter,
  sort,
  setSort,
  view,
  setView,
  boardMetrics,
  onCreateTask,
  onImportGitHub,
  searchInputRef,
}: BoardToolbarProps) {
  return (
    <div className="flex flex-wrap items-center gap-2 border-b border-[color:var(--border-subtle)] pb-3">
      <ToggleGroup
        type="single"
        value={view}
        onValueChange={(value) => {
          if (value === 'kanban' || value === 'backlog') {
            setView(value);
          }
        }}
        variant="outline"
        size="sm"
        aria-label="Board view"
      >
        <ToggleGroupItem value="kanban" aria-label="Kanban view" className="data-[state=on]:bg-[color:var(--foreground)] data-[state=on]:text-[color:var(--background)]">
          <LayoutGrid className="size-3.5" />
          Board
        </ToggleGroupItem>
        <ToggleGroupItem value="backlog" aria-label="Backlog list view" className="data-[state=on]:bg-[color:var(--foreground)] data-[state=on]:text-[color:var(--background)]">
          <ListTodo className="size-3.5" />
          List
        </ToggleGroupItem>
      </ToggleGroup>

      <span className="h-4 w-px bg-[color:var(--border-subtle)]" />

      {view === 'backlog' ? (
        <>
          {(['ALL', ...COLUMN_ORDER] as const).map((value) => (
            <Button
              key={value}
              type="button"
              variant="ghost"
              size="xs"
              className={statusFilter === value ? 'bg-[color:var(--foreground)] text-[color:var(--background)] hover:bg-[color:var(--foreground)]/90 hover:text-[color:var(--background)]' : 'text-[var(--muted-foreground)]'}
              onClick={() => setStatusFilter(value)}
            >
              {value === 'ALL' ? 'All' : STATUS_LABELS[value as TaskStatus]}
            </Button>
          ))}
          <span className="h-4 w-px bg-[color:var(--border-subtle)]" />
        </>
      ) : null}

      <NativeSelect
        value={sort}
        onChange={(e) => setSort(e.target.value as SortOption)}
        className="h-7 min-w-[7rem] border-none bg-transparent px-2 text-xs text-[var(--muted-foreground)] shadow-none"
        aria-label="Sort tasks"
      >
        {(Object.entries(SORT_LABELS) as [SortOption, string][]).map(([value, label]) => (
          <NativeSelectOption key={value} value={value}>{label}</NativeSelectOption>
        ))}
      </NativeSelect>

      <div className="ml-auto flex items-center gap-2">
        <span className="font-code text-[10px] uppercase tracking-wider text-[var(--muted-foreground)]">
          <Radar className="mr-1 inline size-3" />
          {boardMetrics.running} live
        </span>
        <span className="font-code text-[10px] uppercase tracking-wider text-[var(--muted-foreground)]">
          {boardMetrics.readyForReview} ready for review
        </span>

        <div className="relative min-w-[7rem]">
          <Search className="pointer-events-none absolute left-2 top-1/2 size-3.5 -translate-y-1/2 text-[var(--muted-foreground)]" />
          <Input
            ref={searchInputRef}
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="/"
            className="h-7 w-28 border-[color:var(--border-subtle)] bg-transparent pl-7 pr-2 text-xs"
            aria-label="Search tasks"
          />
        </div>

        {onImportGitHub ? (
          <Button variant="outline" size="sm" onClick={onImportGitHub}>
            <Download className="size-3.5" />
            Import
          </Button>
        ) : null}
        <Button size="sm" onClick={onCreateTask}>
          <Plus className="size-3.5" />
          New
        </Button>
      </div>
    </div>
  );
}
