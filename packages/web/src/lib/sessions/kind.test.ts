import { describe, it, expect } from 'vitest';
import { sessionKind, SESSION_KIND_LABEL, SESSION_KIND_BADGE } from './kind';

describe('sessionKind', () => {
  it('narrows known kinds', () => {
    expect(sessionKind({ type: 'orchestrator' })).toBe('orchestrator');
    expect(sessionKind({ type: 'general' })).toBe('general');
    expect(sessionKind({ type: 'task' })).toBe('task');
  });

  it('returns null for unknown values', () => {
    expect(sessionKind({ type: '' })).toBeNull();
    expect(sessionKind({ type: 'agent' })).toBeNull();
    expect(sessionKind({ type: 'ORCHESTRATOR' })).toBeNull();
  });

  it('label and badge maps cover every kind', () => {
    expect(Object.keys(SESSION_KIND_LABEL).sort()).toEqual(['general', 'orchestrator', 'task']);
    expect(Object.keys(SESSION_KIND_BADGE).sort()).toEqual(['general', 'orchestrator', 'task']);
  });
});
