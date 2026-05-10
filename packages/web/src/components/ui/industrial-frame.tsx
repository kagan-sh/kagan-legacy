/**
 * IndustrialFrame — optional CRT-viewport corner-bracket decorator.
 *
 * Renders 12×12 px amber L-bracket corners pinned to two opposing corners of
 * the parent container (top-left + bottom-right). Use at most once per screen.
 *
 * Design-system reference: "industrial framing" — `radial-gradient` / amber
 * phosphor L-shapes at 30% opacity to evoke a CRT viewport.
 *
 * Usage:
 *   <div className="relative">
 *     <IndustrialFrame />
 *     {children}
 *   </div>
 *
 * The parent must be `position: relative` (or otherwise a containing block).
 * This component renders `pointer-events: none` overlays only.
 */

import { cn } from '@/lib/utils';

interface IndustrialFrameProps {
  /** Extra classes applied to each corner bracket element. */
  className?: string;
  /** Amber opacity. Defaults to 0.30 per design spec. */
  opacity?: number;
}

const BRACKET_SIZE = 12;

export function IndustrialFrame({ className, opacity = 0.3 }: IndustrialFrameProps) {
  const color = `rgba(212, 168, 75, ${opacity})`;

  const sharedStyle: React.CSSProperties = {
    position: 'absolute',
    width: BRACKET_SIZE,
    height: BRACKET_SIZE,
    pointerEvents: 'none',
    zIndex: 10,
  };

  return (
    <>
      {/* Top-left */}
      <span
        aria-hidden="true"
        className={cn(className)}
        style={{
          ...sharedStyle,
          top: 0,
          left: 0,
          borderTop: `1px solid ${color}`,
          borderLeft: `1px solid ${color}`,
        }}
      />
      {/* Bottom-right */}
      <span
        aria-hidden="true"
        className={cn(className)}
        style={{
          ...sharedStyle,
          bottom: 0,
          right: 0,
          borderBottom: `1px solid ${color}`,
          borderRight: `1px solid ${color}`,
        }}
      />
    </>
  );
}
