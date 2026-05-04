import { describe, it, expect } from 'vitest';
import { getToolRenderer, TOOL_RENDERERS, BashRenderer, DefaultRenderer } from '@/lib/tool-renderers';

describe('tool renderer registry', () => {
  it('getToolRenderer("bash_exec") returns BashRenderer', () => {
    expect(getToolRenderer('bash_exec')).toBe(BashRenderer);
  });

  it('getToolRenderer("bash") returns BashRenderer', () => {
    expect(getToolRenderer('bash')).toBe(BashRenderer);
  });

  it('getToolRenderer("terminal_run") returns BashRenderer', () => {
    expect(getToolRenderer('terminal_run')).toBe(BashRenderer);
  });

  it('getToolRenderer("unknown_tool") returns DefaultRenderer', () => {
    expect(getToolRenderer('unknown_tool')).toBe(DefaultRenderer);
  });

  it('getToolRenderer("") returns DefaultRenderer for empty string', () => {
    expect(getToolRenderer('')).toBe(DefaultRenderer);
  });

  it('TOOL_RENDERERS map has registered entries', () => {
    expect(TOOL_RENDERERS.size).toBeGreaterThan(0);
    expect(TOOL_RENDERERS.has('bash_exec')).toBe(true);
    expect(TOOL_RENDERERS.has('edit_file')).toBe(true);
    expect(TOOL_RENDERERS.has('read_file')).toBe(true);
    expect(TOOL_RENDERERS.has('apply_diff')).toBe(true);
  });

  it('all registered entries are React function components', () => {
    for (const [, Renderer] of TOOL_RENDERERS) {
      expect(typeof Renderer).toBe('function');
    }
  });
});
