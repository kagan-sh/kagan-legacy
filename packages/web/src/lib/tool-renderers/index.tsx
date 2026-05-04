import type React from 'react';
import { DefaultRenderer } from './default';
import { BashRenderer } from './bash';
import { JsReplRenderer } from './js-repl';
import { DiffRenderer } from './diff';
import { ReadFileRenderer } from './read-file';
import { EditRenderer } from './edit';

// ---------------------------------------------------------------------------
// Shared props type for all tool renderers
// ---------------------------------------------------------------------------

export interface ToolRendererProps {
  toolId: string;
  name: string;
  args: Record<string, unknown> | null;
  /** Live partial output during streaming (e.g. bash stdout so far). */
  partialResult: string | null;
  status: 'running' | 'completed' | 'failed';
  result: string | null;
}

// ---------------------------------------------------------------------------
// Registry — plain const Map, no runtime register() API (YAGNI).
// Add tool names here when a new renderer is built; unregistered tools
// automatically fall back to DefaultRenderer.
// ---------------------------------------------------------------------------

export const TOOL_RENDERERS = new Map<string, React.FC<ToolRendererProps>>([
  ['bash_exec', BashRenderer],
  ['bash', BashRenderer],
  ['terminal_run', BashRenderer],
  ['js_repl', JsReplRenderer],
  ['edit_file', EditRenderer],
  ['str_replace_editor', EditRenderer],
  ['read_file', ReadFileRenderer],
  ['apply_diff', DiffRenderer],
  ['patch', DiffRenderer],
]);

// ---------------------------------------------------------------------------
// Lookup helper — callers never touch the Map directly
// ---------------------------------------------------------------------------

export function getToolRenderer(name: string): React.FC<ToolRendererProps> {
  return TOOL_RENDERERS.get(name) ?? DefaultRenderer;
}

// Re-export renderers so consumers can reference them without going through
// individual files (needed in tests).
export { DefaultRenderer } from './default';
export { BashRenderer } from './bash';
export { JsReplRenderer } from './js-repl';
export { DiffRenderer } from './diff';
export { ReadFileRenderer } from './read-file';
export { EditRenderer } from './edit';
