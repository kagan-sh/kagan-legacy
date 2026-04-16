import type { ComponentPropsWithoutRef, ElementType, ReactNode } from 'react';

type VisuallyHiddenProps<T extends ElementType = 'span'> = {
  as?: T;
  children: ReactNode;
} & Omit<ComponentPropsWithoutRef<T>, 'as' | 'children'>;

const style: React.CSSProperties = {
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
export function VisuallyHidden<T extends ElementType = 'span'>({
  as,
  children,
  ...rest
}: VisuallyHiddenProps<T>) {
  const Tag = (as ?? 'span') as ElementType;
  return (
    <Tag style={style} {...rest}>
      {children}
    </Tag>
  );
}
