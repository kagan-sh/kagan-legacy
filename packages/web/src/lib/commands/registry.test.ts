import { afterAll, beforeEach, describe, expect, it, vi } from 'vitest';
import { Plus } from 'lucide-react';
import {
  __resetRegistryForTests,
  getCommand,
  getCommands,
  registerCommand,
  unregisterCommand,
} from '@/lib/commands/registry';
import {
  BUILTIN_COMMANDS,
  __resetBuiltinRegistrationForTests,
  registerBuiltinCommands,
} from '@/lib/commands/commands';
import { store } from '@/lib/atoms/store';
import { tasksAtom, boardDialogAtom } from '@/lib/atoms/board';
import {
  helpOverlayOpenAtom,
  integrationImportOpenAtom,
  sessionPickerOpenAtom,
} from '@/lib/atoms/ui';
import type { CommandAction } from '@/lib/commands/types';
import type { WireTask } from '@kagan/shared-api-client';

function makeAction(overrides: Partial<CommandAction> = {}): CommandAction {
  return {
    id: overrides.id ?? 'test-action',
    title: overrides.title ?? 'Test action',
    section: overrides.section ?? 'Navigate',
    handler: overrides.handler ?? vi.fn(),
    ...overrides,
  };
}

describe('command registry', () => {
  beforeEach(() => {
    __resetRegistryForTests();
    __resetBuiltinRegistrationForTests();
  });

  it('registers and retrieves commands by id', () => {
    const action = makeAction({ id: 'nav-board', title: 'Board' });
    registerCommand(action);

    expect(getCommand('nav-board')).toBe(action);
    expect(getCommands()).toHaveLength(1);
  });

  it('requires a non-empty id', () => {
    expect(() => registerCommand(makeAction({ id: '' }))).toThrow(/id is required/);
  });

  it('replaces an existing action when the same id is registered again', () => {
    registerCommand(makeAction({ id: 'dup', title: 'First' }));
    registerCommand(makeAction({ id: 'dup', title: 'Second' }));

    expect(getCommand('dup')?.title).toBe('Second');
    expect(getCommands()).toHaveLength(1);
  });

  it('unregisters commands', () => {
    registerCommand(makeAction({ id: 'to-remove' }));
    unregisterCommand('to-remove');

    expect(getCommand('to-remove')).toBeUndefined();
    expect(getCommands()).toHaveLength(0);
  });

  it('unregister is idempotent for unknown ids', () => {
    expect(() => unregisterCommand('never-registered')).not.toThrow();
  });

  it('returned unregister function removes the action', () => {
    const off = registerCommand(makeAction({ id: 'auto' }));
    expect(getCommands()).toHaveLength(1);

    off();
    expect(getCommands()).toHaveLength(0);
  });

  it('filters out commands whose when() returns false', () => {
    registerCommand(makeAction({ id: 'hidden', when: () => false }));
    registerCommand(makeAction({ id: 'visible', when: () => true }));
    registerCommand(makeAction({ id: 'always' }));

    const visible = getCommands().map((a) => a.id).sort();
    expect(visible).toEqual(['always', 'visible']);
  });

  it('getCommands returns a fresh array per call', () => {
    registerCommand(makeAction({ id: 'a' }));
    const first = getCommands();
    const second = getCommands();
    expect(first).not.toBe(second);
  });

  it('carries optional icon and shortcut fields through untouched', () => {
    const action = makeAction({
      id: 'with-extras',
      icon: Plus,
      shortcut: ['⌘', 'K'],
      keywords: ['create', 'new'],
    });
    registerCommand(action);
    const fetched = getCommand('with-extras');
    expect(fetched?.icon).toBe(Plus);
    expect(fetched?.shortcut).toEqual(['⌘', 'K']);
    expect(fetched?.keywords).toEqual(['create', 'new']);
  });
});

describe('registerBuiltinCommands', () => {
  beforeEach(() => {
    __resetRegistryForTests();
    __resetBuiltinRegistrationForTests();
  });

  it('registers every built-in command', () => {
    registerBuiltinCommands();

    // getCommands() filters by when(), so pull direct registrations instead.
    const ids = BUILTIN_COMMANDS
      .map((a) => a.id)
      .filter((id) => getCommand(id) !== undefined)
      .sort();
    const expected = BUILTIN_COMMANDS.map((a) => a.id).sort();
    expect(ids).toEqual(expected);
  });

  it('is idempotent — second call registers no duplicates', () => {
    registerBuiltinCommands();
    registerBuiltinCommands();

    const present = BUILTIN_COMMANDS
      .map((a) => a.id)
      .filter((id) => getCommand(id) !== undefined);
    expect(present).toHaveLength(BUILTIN_COMMANDS.length);
  });

  it('uses kebab-case ids', () => {
    for (const action of BUILTIN_COMMANDS) {
      expect(action.id).toMatch(/^[a-z0-9]+(-[a-z0-9]+)*$/);
    }
  });

  it('assigns every built-in to a known section', () => {
    const allowed = new Set(['Navigate', 'Create', 'Run', 'Settings', 'Help']);
    for (const action of BUILTIN_COMMANDS) {
      expect(allowed.has(action.section)).toBe(true);
    }
  });

  it('registers session switcher, GitHub import, and help migrations', () => {
    registerBuiltinCommands();

    expect(getCommand('nav-session-switcher')).toBeDefined();
    expect(getCommand('create-github-import')).toBeDefined();
    expect(getCommand('help-shortcuts')).toBeDefined();
  });

  it('registers agent + review actions in the Run section', () => {
    registerBuiltinCommands();

    const ids = [
      'run-start-current-task',
      'run-stop-current-task',
      'run-review-approve',
      'run-review-reject',
      'run-review-merge',
    ];
    for (const id of ids) {
      const action = getCommand(id);
      expect(action, `missing command ${id}`).toBeDefined();
      expect(action?.section).toBe('Run');
    }
  });

  it('registers task-scoped edit and delete commands in the Create section', () => {
    registerBuiltinCommands();

    expect(getCommand('create-edit-current-task')?.section).toBe('Create');
    expect(getCommand('create-delete-current-task')?.section).toBe('Create');
  });
});

describe('task-scoped command guards', () => {
  const originalPath = window.location.pathname;

  beforeEach(() => {
    __resetRegistryForTests();
    __resetBuiltinRegistrationForTests();
    store.set(tasksAtom, []);
    window.history.replaceState(null, '', '/board');
  });

  afterAll(() => {
    window.history.replaceState(null, '', originalPath);
  });

  function makeTask(overrides: Partial<WireTask> = {}): WireTask {
    return {
      id: 'task-1',
      title: 'Example task',
      description: '',
      status: 'BACKLOG',
      priority: 'MEDIUM',
      active_session: null,
      ...overrides,
    } as WireTask;
  }

  it('hides task-scoped commands when no task route is active', () => {
    registerBuiltinCommands();
    const visible = new Set(getCommands().map((c) => c.id));

    expect(visible.has('nav-task-open')).toBe(false);
    expect(visible.has('create-edit-current-task')).toBe(false);
    expect(visible.has('create-delete-current-task')).toBe(false);
    expect(visible.has('run-start-current-task')).toBe(false);
    expect(visible.has('run-stop-current-task')).toBe(false);
    expect(visible.has('run-review-approve')).toBe(false);
    expect(visible.has('run-review-reject')).toBe(false);
    expect(visible.has('run-review-merge')).toBe(false);
  });

  it('does not treat session routes as task routes', () => {
    window.history.replaceState(null, '', '/session/task-1');
    store.set(tasksAtom, [makeTask({ status: 'BACKLOG' })]);
    registerBuiltinCommands();

    const visible = new Set(getCommands().map((c) => c.id));
    expect(visible.has('nav-task-open')).toBe(false);
    expect(visible.has('run-start-current-task')).toBe(false);
  });

  it('exposes start + edit + delete when viewing a backlog task', () => {
    window.history.replaceState(null, '', '/task/task-1');
    store.set(tasksAtom, [makeTask({ status: 'BACKLOG' })]);
    registerBuiltinCommands();

    const visible = new Set(getCommands().map((c) => c.id));
    expect(visible.has('nav-task-open')).toBe(true);
    expect(visible.has('create-edit-current-task')).toBe(true);
    expect(visible.has('create-delete-current-task')).toBe(true);
    expect(visible.has('run-start-current-task')).toBe(true);
    expect(visible.has('run-stop-current-task')).toBe(false);
    expect(visible.has('run-review-approve')).toBe(false);
  });

  it('exposes stop only when an active session is running', () => {
    window.history.replaceState(null, '', '/task/task-1');
    store.set(tasksAtom, [
      makeTask({
        status: 'IN_PROGRESS',
        active_session: {
          id: 'sess-1',
          status: 'RUNNING',
          agent_backend: 'claude-code',
          started_at: '2024-01-01T00:00:00Z',
        },
      }),
    ]);
    registerBuiltinCommands();

    const visible = new Set(getCommands().map((c) => c.id));
    expect(visible.has('run-stop-current-task')).toBe(true);
    expect(visible.has('run-start-current-task')).toBe(true);
  });

  it('hides start for DONE tasks', () => {
    window.history.replaceState(null, '', '/task/task-1');
    store.set(tasksAtom, [makeTask({ status: 'DONE' })]);
    registerBuiltinCommands();

    const visible = new Set(getCommands().map((c) => c.id));
    expect(visible.has('run-start-current-task')).toBe(false);
  });

  it('exposes review actions when the task is in REVIEW', () => {
    window.history.replaceState(null, '', '/task/task-1');
    store.set(tasksAtom, [makeTask({ status: 'REVIEW' })]);
    registerBuiltinCommands();

    const visible = new Set(getCommands().map((c) => c.id));
    expect(visible.has('run-review-approve')).toBe(true);
    expect(visible.has('run-review-reject')).toBe(true);
    expect(visible.has('run-review-merge')).toBe(true);
  });
});

describe('command handlers flip global atoms', () => {
  beforeEach(() => {
    __resetRegistryForTests();
    __resetBuiltinRegistrationForTests();
    store.set(sessionPickerOpenAtom, false);
    store.set(integrationImportOpenAtom, false);
    store.set(helpOverlayOpenAtom, false);
    store.set(boardDialogAtom, { kind: 'none' });
  });

  function invoke(id: string) {
    const action = getCommand(id);
    expect(action, `missing command ${id}`).toBeDefined();
    void action!.handler({ navigate: vi.fn() });
  }

  it('opens the session switcher', () => {
    registerBuiltinCommands();
    invoke('nav-session-switcher');
    expect(store.get(sessionPickerOpenAtom)).toBe(true);
  });

  it('opens the GitHub import dialog', () => {
    registerBuiltinCommands();
    invoke('create-github-import');
    expect(store.get(integrationImportOpenAtom)).toBe(true);
  });

  it('opens the help overlay', () => {
    registerBuiltinCommands();
    invoke('help-shortcuts');
    expect(store.get(helpOverlayOpenAtom)).toBe(true);
  });

  it('opens the create-task dialog', () => {
    registerBuiltinCommands();
    invoke('create-task');
    expect(store.get(boardDialogAtom)).toEqual({ kind: 'create' });
  });
});
