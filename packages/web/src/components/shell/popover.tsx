/**
 * Shell popover primitive.
 *
 * Renders at `position: fixed` anchored to a trigger element via x/y
 * coordinates captured from a MouseEvent. The popover floats above all shell
 * chrome (z-index 200) and is positioned either left-aligned or right-aligned
 * to its trigger depending on `anchor.align`.
 *
 * State lives in `shellPopoverAtom` — a single discriminated union so that
 * only one popover can be open at a time (opening a new one closes the
 * previous implicitly). The `useShellPopover` hook is the only public API
 * consumers should use.
 */

import { useEffect, useRef, useCallback } from 'react';
import { useAtom } from 'jotai';
import { cn } from '@/lib/utils';
import { shellPopoverAtom, type ShellPopover, type PopoverAnchor } from '@/lib/atoms/shell';

// ---------------------------------------------------------------------------
// Public hook
// ---------------------------------------------------------------------------

export interface UseShellPopoverReturn {
  isOpen: boolean;
  openFromEvent: (e: React.MouseEvent<HTMLElement>) => void;
  close: () => void;
}

/**
 * Bind a trigger element to a named popover slot.
 *
 * @param kind  The popover discriminant that this hook controls.
 * @param align Whether to align the popover left or right of the trigger.
 */
export function useShellPopover(
  kind: Exclude<ShellPopover, null>,
  align: PopoverAnchor['align'] = 'left',
): UseShellPopoverReturn {
  const [state, setState] = useAtom(shellPopoverAtom);
  const isOpen = state.kind === kind;

  const openFromEvent = useCallback(
    (e: React.MouseEvent<HTMLElement>) => {
      const rect = e.currentTarget.getBoundingClientRect();
      const anchor: PopoverAnchor = {
        x: align === 'left' ? rect.left : rect.right,
        y: rect.bottom + 6,
        align,
      };
      setState((prev) =>
        prev.kind === kind ? { kind: null, anchor: null } : { kind, anchor },
      );
    },
    [kind, align, setState],
  );

  const close = useCallback(() => {
    setState((prev) => (prev.kind === kind ? { kind: null, anchor: null } : prev));
  }, [kind, setState]);

  return { isOpen, openFromEvent, close };
}

// ---------------------------------------------------------------------------
// Container — render once in the shell, mounts/unmounts the active popover
// ---------------------------------------------------------------------------

interface ShellPopoverContainerProps {
  children: React.ReactNode;
}

/**
 * Single fixed-position portal for shell popovers. Place once in the shell
 * (e.g. ShellLayout). Children receive visibility through the atom.
 */
export function ShellPopoverContainer({ children }: ShellPopoverContainerProps) {
  return <>{children}</>;
}

// ---------------------------------------------------------------------------
// Popover panel
// ---------------------------------------------------------------------------

interface PopoverPanelProps {
  kind: Exclude<ShellPopover, null>;
  /** Minimum panel width in px (default 220). */
  minWidth?: number;
  className?: string;
  children: React.ReactNode;
}

/**
 * Renders the popover panel for `kind`. Closes on outside click, Escape, or
 * when the atom's kind changes to something else.
 */
export function PopoverPanel({ kind, minWidth = 220, className, children }: PopoverPanelProps) {
  const [state, setState] = useAtom(shellPopoverAtom);
  const ref = useRef<HTMLDivElement>(null);

  const isOpen = state.kind === kind;
  const anchor = isOpen ? state.anchor : null;

  const close = useCallback(() => {
    setState((prev) => (prev.kind === kind ? { kind: null, anchor: null } : prev));
  }, [kind, setState]);

  // Close on Escape
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === 'Escape') {
        e.stopPropagation();
        close();
      }
    };
    document.addEventListener('keydown', handler, { capture: true });
    return () => document.removeEventListener('keydown', handler, { capture: true });
  }, [isOpen, close]);

  // Close on outside click
  useEffect(() => {
    if (!isOpen) return;
    const handler = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) {
        close();
      }
    };
    // Use mousedown so the popover dismisses before the click registers on the outside target
    document.addEventListener('mousedown', handler);
    return () => document.removeEventListener('mousedown', handler);
  }, [isOpen, close]);

  if (!isOpen || !anchor) return null;

  const style: React.CSSProperties = {
    position: 'fixed',
    top: anchor.y,
    zIndex: 200,
    minWidth,
    ...(anchor.align === 'left'
      ? { left: anchor.x }
      : { right: `calc(100vw - ${anchor.x}px)` }),
  };

  return (
    <div
      ref={ref}
      role="menu"
      aria-modal={false}
      style={style}
      className={cn(
        'rounded-lg border border-[var(--border)] bg-[var(--popover)] p-1.5',
        'shadow-[0_12px_32px_-8px_rgba(0,0,0,0.7),0_4px_12px_rgba(0,0,0,0.4)]',
        '[animation:pop-in_140ms_ease-out]',
        className,
      )}
    >
      {children}
    </div>
  );
}

// ---------------------------------------------------------------------------
// Shared sub-components used by every popover
// ---------------------------------------------------------------------------

/** Dim section title label inside a popover. */
export function PopoverTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-2.5 pb-2 pt-1.5 font-code text-[10px] font-semibold uppercase tracking-[0.18em] text-[var(--muted-foreground)]">
      {children}
    </div>
  );
}

interface PopoverItemProps {
  icon: React.ReactNode;
  label: string;
  desc?: string;
  active?: boolean;
  danger?: boolean;
  onClick: () => void;
  'aria-label'?: string;
}

/** Standard icon + label + optional desc row inside a popover. */
export function PopoverItem({
  icon,
  label,
  desc,
  active,
  danger,
  onClick,
  'aria-label': ariaLabel,
}: PopoverItemProps) {
  return (
    <button
      type="button"
      role="menuitem"
      data-active={active ? 'true' : 'false'}
      aria-label={ariaLabel ?? label}
      onClick={onClick}
      className={cn(
        'flex w-full items-center gap-2.5 rounded-md border-0 bg-transparent px-2.5 py-2 text-left font-ui text-[12.5px] transition-colors',
        danger
          ? 'text-[#e85535] hover:bg-[rgba(232,85,53,0.08)]'
          : 'text-[var(--fg-2)] hover:bg-[var(--surface-2)] hover:text-[var(--foreground)]',
        active && 'bg-[var(--surface-2)]',
      )}
    >
      <span className="grid size-[18px] shrink-0 place-items-center font-code text-[11px] font-bold">
        {icon}
      </span>
      <span className="flex-1 min-w-0">
        {label}
        {desc ? (
          <span className="mt-0.5 block font-code text-[11px] text-[var(--muted-foreground)] tracking-[0.02em]">
            {desc}
          </span>
        ) : null}
      </span>
      {active ? (
        <span className="ml-auto font-code text-[11px] text-[var(--primary)]">✓</span>
      ) : null}
    </button>
  );
}

/** Thin horizontal rule between popover sections. */
export function PopoverSeparator() {
  return <hr className="my-1 border-t border-[var(--border)]" />;
}
