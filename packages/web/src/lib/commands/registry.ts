/**
 * Module-level command registry.
 *
 * This is a plain Map keyed by `action.id`. No React state — the palette
 * simply reads `getCommands()` whenever it opens. Registration is idempotent:
 * re-registering the same id replaces the previous entry.
 *
 * Exported as functions (not a class) so tests can clear between runs and
 * so consumers can't accidentally mutate the underlying Map.
 */
import type { CommandAction } from '@/lib/commands/types';

const registry = new Map<string, CommandAction>();

/** Register (or replace) a command. Returns an unregister function. */
export function registerCommand(action: CommandAction): () => void {
  if (!action.id) {
    throw new Error('registerCommand: action.id is required');
  }
  registry.set(action.id, action);
  return () => unregisterCommand(action.id);
}

/** Remove a command by id. Silently no-ops if the id is unknown. */
export function unregisterCommand(id: string): void {
  registry.delete(id);
}

/**
 * Snapshot of all currently-registered commands.
 *
 * Filters out any command whose `when()` returns false. The array is a
 * fresh copy each call — safe to sort/mutate on the receiving side.
 */
export function getCommands(): CommandAction[] {
  const out: CommandAction[] = [];
  for (const action of registry.values()) {
    if (action.when && !action.when()) continue;
    out.push(action);
  }
  return out;
}

/** Look up a single command by id. */
export function getCommand(id: string): CommandAction | undefined {
  return registry.get(id);
}

/** Wipe the registry. Test-only; do not call from app code. */
export function __resetRegistryForTests(): void {
  registry.clear();
}
