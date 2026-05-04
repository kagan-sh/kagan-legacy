import { describe, it, expect } from 'vitest';
import { STATUS_LABELS, STATUS_COLORS, PRIORITY_GLYPHS } from '@/lib/utils/constants';

describe('D2: CANCELLED status constants', () => {
  it('STATUS_LABELS includes CANCELLED', () => {
    expect(STATUS_LABELS['CANCELLED']).toBe('Cancelled');
  });

  it('STATUS_COLORS includes CANCELLED mapped to idle rail token', () => {
    expect(STATUS_COLORS['CANCELLED']).toBe('var(--kagan-rail-idle)');
  });

  it('STATUS_LABELS still contains all four core statuses', () => {
    expect(STATUS_LABELS['BACKLOG']).toBe('Backlog');
    expect(STATUS_LABELS['IN_PROGRESS']).toBe('In Progress');
    expect(STATUS_LABELS['REVIEW']).toBe('Review');
    expect(STATUS_LABELS['DONE']).toBe('Done');
  });
});

describe('D10: PRIORITY_GLYPHS', () => {
  it('HIGH maps to ▲', () => {
    expect(PRIORITY_GLYPHS['HIGH']).toBe('▲');
  });

  it('MEDIUM maps to —', () => {
    expect(PRIORITY_GLYPHS['MEDIUM']).toBe('—');
  });

  it('LOW maps to ▼', () => {
    expect(PRIORITY_GLYPHS['LOW']).toBe('▼');
  });
});
