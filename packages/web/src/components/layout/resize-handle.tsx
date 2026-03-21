import { useCallback, useRef } from 'react';
import { cn } from '@/lib/utils';

type Edge = 'left' | 'top';

interface ResizeHandleProps {
  /** Which edge the handle sits on — determines drag axis. */
  edge: Edge;
  /** Called continuously during drag with the signed pixel delta (negative = shrink). */
  onResize: (delta: number) => void;
  className?: string;
}

/**
 * Thin drag handle placed on the left or top edge of a resizable panel.
 * Renders a 4px interaction strip with a visible 2px line on hover.
 */
export function ResizeHandle({ edge, onResize, className }: ResizeHandleProps) {
  const startRef = useRef(0);

  const onPointerDown = useCallback(
    (e: React.PointerEvent) => {
      e.preventDefault();
      const target = e.currentTarget as HTMLElement;
      target.setPointerCapture(e.pointerId);
      startRef.current = edge === 'left' ? e.clientX : e.clientY;
    },
    [edge],
  );

  const onPointerMove = useCallback(
    (e: React.PointerEvent) => {
      if (!(e.currentTarget as HTMLElement).hasPointerCapture(e.pointerId)) return;
      const current = edge === 'left' ? e.clientX : e.clientY;
      const delta = startRef.current - current; // positive = grow panel
      startRef.current = current;
      onResize(delta);
    },
    [edge, onResize],
  );

  const isHorizontal = edge === 'left';

  return (
    <div
      role="separator"
      aria-orientation={isHorizontal ? 'vertical' : 'horizontal'}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      className={cn(
        'group absolute z-10 select-none',
        isHorizontal
          ? 'inset-y-0 left-0 w-1.5 cursor-col-resize'
          : 'inset-x-0 top-0 h-1.5 cursor-row-resize',
        className,
      )}
    >
      <div
        className={cn(
          'absolute bg-[var(--primary)] opacity-0 transition-opacity duration-150 group-hover:opacity-60 group-active:opacity-100',
          isHorizontal ? 'inset-y-0 left-0 w-[2px]' : 'inset-x-0 top-0 h-[2px]',
        )}
      />
    </div>
  );
}
