import { describe, expect, it } from 'vitest';
import appCss from '../../app.css?raw';

import { focusRing } from './focus-ring';

describe('focusRing utility', () => {
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

describe('D5: single focus ring system', () => {
  it('app.css does not contain a global :focus-visible rule that would override focusRing', () => {
    // The global :focus-visible rule was deleted so focusRing is the sole system.
    // Ensure the deleted rule (using --focus-ring box-shadow) is gone.
    expect(appCss).not.toContain('box-shadow: 0 0 0 4px var(--focus-ring)');
  });
});
