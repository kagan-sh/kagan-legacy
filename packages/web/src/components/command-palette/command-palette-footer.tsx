import { Kbd } from '@/components/ui/kbd';

/**
 * Static helper strip at the bottom of the palette. Keyboard hints only —
 * no interactive controls.
 */
export function CommandPaletteFooter() {
  return (
    <div
      data-slot="command-palette-footer"
      className="flex items-center justify-between gap-3 border-t border-[color:var(--border-subtle)] bg-[color:color-mix(in_oklab,var(--surface-1)_60%,var(--card))] px-3 py-2 text-xs text-[var(--muted-foreground)]"
    >
      <div className="flex items-center gap-3">
        <span className="flex items-center gap-1">
          <Kbd>↑</Kbd>
          <Kbd>↓</Kbd>
          <span>navigate</span>
        </span>
        <span className="flex items-center gap-1">
          <Kbd>↵</Kbd>
          <span>select</span>
        </span>
        <span className="flex items-center gap-1">
          <Kbd>esc</Kbd>
          <span>close</span>
        </span>
      </div>
    </div>
  );
}
