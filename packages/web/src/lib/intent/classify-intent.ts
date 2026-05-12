/**
 * Keyword-based intent classifier for the home hero input.
 *
 * Design rule (Andrew Ng): keep it simple — heuristics first, no LLM.
 * Upgrade only when we can measure a win over this baseline.
 */

export type IntentKind =
  | 'create-task'
  | 'search'
  | 'chat'
  | 'navigate-settings'
  | 'navigate-board'
  | 'navigate-workspace'
  | 'unknown';

export interface ClassifiedIntent {
  kind: IntentKind;
  /** 0-1, rough heuristic score for UI affordance only. */
  confidence: number;
  /** The route the primary action should navigate to on submit. */
  route: string;
  /** Short, user-facing action label (e.g. "Create task"). */
  label: string;
  /** Optional fields pulled out of the input (title, description). */
  extractedFields?: {
    title?: string;
    description?: string;
  };
}

// Ordered: most specific first.
const IMPERATIVE_VERBS = [
  'add',
  'fix',
  'refactor',
  'optimize',
  'optimise',
  'investigate',
  'document',
  'implement',
  'build',
  'create',
  'remove',
  'delete',
  'rename',
  'migrate',
  'upgrade',
  'bump',
  'rewrite',
  'extract',
  'inline',
  'test',
  'write',
];

const QUESTION_STARTERS = ['how', 'what', 'why', 'where', 'when', 'who', 'can', 'should', 'is', 'does'];

const SEARCH_MARKERS = ['find', 'search for', 'search ', 'where is', 'look for', 'locate'];

interface NavRule {
  kind: IntentKind;
  route: string;
  label: string;
  triggers: readonly string[];
}

const NAV_RULES: readonly NavRule[] = [
  { kind: 'navigate-settings', route: '/settings', label: 'Open settings', triggers: ['settings', 'preferences', 'config'] },
  { kind: 'navigate-board', route: '/board', label: 'Open board', triggers: ['board', 'kanban', 'tasks list'] },
  { kind: 'navigate-workspace', route: '/workspace', label: 'Open workspace', triggers: ['workspace', 'conversations', 'chats'] },
];

const NAV_VERBS = ['show', 'open', 'go to', 'take me to', 'navigate to', 'jump to'];

function firstWord(s: string): string {
  const trimmed = s.trim().toLowerCase();
  const space = trimmed.indexOf(' ');
  return space === -1 ? trimmed : trimmed.slice(0, space);
}

function stripTrailingPunctuation(s: string): string {
  return s.replace(/[.?!]+$/u, '').trim();
}

function capitalizeFirst(s: string): string {
  if (!s) return s;
  return s.charAt(0).toUpperCase() + s.slice(1);
}

export const UNKNOWN_INTENT: ClassifiedIntent = {
  kind: 'unknown',
  confidence: 0,
  route: '/workspace',
  label: 'Open chat',
};

/**
 * Classify a free-form user utterance into a routing intent.
 *
 * Returns a stable {@link UNKNOWN_INTENT} for empty strings so callers can
 * render an aria-live message without null checks.
 */
export function classifyIntent(input: string): ClassifiedIntent {
  const raw = input.trim();
  if (!raw) return UNKNOWN_INTENT;

  const lower = raw.toLowerCase();
  const head = firstWord(lower);

  // Navigation — "open settings", "go to board".
  if (NAV_VERBS.some((v) => lower.startsWith(v))) {
    for (const rule of NAV_RULES) {
      if (rule.triggers.some((t) => lower.includes(t))) {
        return {
          kind: rule.kind,
          confidence: 0.9,
          route: rule.route,
          label: rule.label,
        };
      }
    }
  }

  // Search — "find X", "search for X", "where is X".
  if (SEARCH_MARKERS.some((m) => lower.startsWith(m))) {
    return {
      kind: 'search',
      confidence: 0.75,
      route: '/board',
      label: 'Search tasks',
    };
  }

  // Question — starts with a question word or contains "?".
  const endsWithQuestionMark = raw.endsWith('?');
  if (endsWithQuestionMark || QUESTION_STARTERS.includes(head)) {
    return {
      kind: 'chat',
      confidence: endsWithQuestionMark && QUESTION_STARTERS.includes(head) ? 0.9 : 0.7,
      route: '/workspace',
      label: 'Ask in chat',
    };
  }

  // Imperative — "add dark mode", "fix flaky tests".
  if (IMPERATIVE_VERBS.includes(head)) {
    const title = capitalizeFirst(stripTrailingPunctuation(raw));
    return {
      kind: 'create-task',
      confidence: 0.85,
      route: '/board',
      label: 'Create task',
      extractedFields: { title },
    };
  }

  // Fallback for longer free-form input that reads like a task description.
  // A whole sentence without a clear trigger is most usefully a task.
  const wordCount = raw.split(/\s+/u).length;
  if (wordCount >= 4) {
    const title = capitalizeFirst(stripTrailingPunctuation(raw));
    return {
      kind: 'create-task',
      confidence: 0.45,
      route: '/board',
      label: 'Create task',
      extractedFields: { title },
    };
  }

  return { ...UNKNOWN_INTENT, confidence: 0.2 };
}

/**
 * User-facing description of a classified intent. Shared by the visible chip
 * and the live-region announcement so sighted and screen-reader users get
 * identical copy.
 */
export function describeIntent(intent: ClassifiedIntent, rawInput: string): string {
  switch (intent.kind) {
    case 'create-task':
      return `Create task: ${intent.extractedFields?.title ?? rawInput}`;
    case 'chat':
      return 'Ask in chat';
    case 'search':
      return `Search tasks for "${rawInput}"`;
    case 'navigate-settings':
      return 'Open settings';
    case 'navigate-board':
      return 'Open board';
    case 'navigate-workspace':
      return 'Open workspace';
    case 'unknown':
      return 'Open chat';
  }
}
