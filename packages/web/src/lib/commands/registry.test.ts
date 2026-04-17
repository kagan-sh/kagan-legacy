import { beforeEach, describe, expect, it, vi } from 'vitest';
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
import type { CommandAction } from '@/lib/commands/types';

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

    const ids = getCommands().map((a) => a.id).sort();
    const expected = BUILTIN_COMMANDS.map((a) => a.id).sort();
    expect(ids).toEqual(expected);
  });

  it('is idempotent — second call registers no duplicates', () => {
    registerBuiltinCommands();
    registerBuiltinCommands();

    expect(getCommands()).toHaveLength(BUILTIN_COMMANDS.length);
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
});
