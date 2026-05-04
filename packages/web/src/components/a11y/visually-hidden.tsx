import type { ComponentPropsWithoutRef, CSSProperties, ReactNode } from 'react';

type VisuallyHiddenProps = {
  children: ReactNode;
} & Omit<ComponentPropsWithoutRef<'span'>, 'children'>;

const style: CSSProperties = {
  position: 'absolute',
  width: 1,
  height: 1,
  padding: 0,
  margin: -1,
  overflow: 'hidden',
  clip: 'rect(0, 0, 0, 0)',
  whiteSpace: 'nowrap',
  border: 0,
};

/**
 * Hides content visually while keeping it available to assistive tech.
 */
export function VisuallyHidden({
  children,
  ...rest
}: VisuallyHiddenProps) {
  return (
    <span style={style} {...rest}>
      {children}
    </span>
  );
}
