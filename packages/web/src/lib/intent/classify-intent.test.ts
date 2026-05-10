import { describe, expect, it } from 'vitest';
import { classifyIntent, UNKNOWN_INTENT } from '@/lib/intent/classify-intent';

describe('classifyIntent', () => {
  it('returns the unknown sentinel for empty input', () => {
    expect(classifyIntent('')).toBe(UNKNOWN_INTENT);
    expect(classifyIntent('   ')).toBe(UNKNOWN_INTENT);
  });

  it('classifies imperative verbs as create-task with the input as title', () => {
    const result = classifyIntent('add dark mode toggle');
    expect(result.kind).toBe('create-task');
    expect(result.route).toBe('/board');
    expect(result.extractedFields?.title).toBe('Add dark mode toggle');
    expect(result.confidence).toBeGreaterThan(0.7);
  });

  it.each([
    ['fix the flaky worker test'],
    ['refactor the agent registry'],
    ['optimize board rendering'],
    ['investigate merge timeouts'],
    ['document the chat protocol'],
  ])('treats "%s" as create-task', (input) => {
    expect(classifyIntent(input).kind).toBe('create-task');
  });

  it('strips trailing punctuation from extracted titles', () => {
    const result = classifyIntent('add dark mode toggle.');
    expect(result.extractedFields?.title).toBe('Add dark mode toggle');
  });

  it('routes questions to chat', () => {
    expect(classifyIntent('how do I cancel a running task?').kind).toBe('chat');
    expect(classifyIntent('what is an orchestrator session').kind).toBe('chat');
    expect(classifyIntent('is my project ready').kind).toBe('chat');
  });

  it('classifies bare "?" sentences as chat', () => {
    expect(classifyIntent('kagan dark mode?').kind).toBe('chat');
  });

  it('routes search phrases to the board search', () => {
    expect(classifyIntent('find the task about OAuth').kind).toBe('search');
    expect(classifyIntent('search for flaky tests').kind).toBe('search');
    expect(classifyIntent('where is the wire schema').kind).toBe('search');
  });

  it('routes navigation phrases to the matching surface', () => {
    expect(classifyIntent('show settings').route).toBe('/settings');
    expect(classifyIntent('go to the board').route).toBe('/board');
    expect(classifyIntent('take me to workspace').route).toBe('/workspace');
  });

  it('falls back to create-task for multi-word free-form sentences', () => {
    const result = classifyIntent('dark mode toggle for mobile');
    expect(result.kind).toBe('create-task');
    expect(result.confidence).toBeLessThan(0.6);
  });

  it('returns unknown for short cryptic input', () => {
    const result = classifyIntent('foo');
    expect(result.kind).toBe('unknown');
    expect(result.confidence).toBeLessThan(0.5);
  });

  it('includes a user-facing label for every non-empty input', () => {
    for (const input of ['add x', 'how does x work?', 'find x', 'open settings', 'foo']) {
      const r = classifyIntent(input);
      expect(r.label.length).toBeGreaterThan(0);
    }
  });
});
