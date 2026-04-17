import { describe, expect, it } from 'vitest';

import { focusRing } from './focus-ring';

describe('focusRing', () => {
  it('clears the native outline on focus-visible', () => {
    expect(focusRing).toContain('focus-visible:outline-none');
  });

  it('paints a 2px ring from the --a11y-focus-ring token', () => {
    expect(focusRing).toContain('focus-visible:ring-2');
    expect(focusRing).toContain('focus-visible:ring-[color:var(--a11y-focus-ring)]');
  });

  it('offsets the ring from the --a11y-focus-ring-offset token', () => {
    expect(focusRing).toContain('focus-visible:ring-offset-2');
    expect(focusRing).toContain('focus-visible:ring-offset-[color:var(--a11y-focus-ring-offset)]');
  });
});
