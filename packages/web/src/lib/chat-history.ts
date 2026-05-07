/**
 * ChatHistory — persists submitted chat messages to localStorage so the user
 * can cycle through them with Up/Down arrow keys.
 *
 * Configuration:
 *   - When `persist` is true (default), entries are stored under
 *     `kagan:chat-history:{projectId}` in localStorage.
 *   - When `persist` is false, an in-memory array is used for the session only.
 *
 * Gracefully falls back to in-memory storage when localStorage is unavailable.
 */

const MAX_ENTRIES = 200;

function storageKey(projectId: string): string {
  return `kagan:chat-history:${projectId}`;
}

function tryReadStorage(key: string): string[] {
  try {
    const raw = localStorage.getItem(key);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((item): item is string => typeof item === 'string');
  } catch {
    return [];
  }
}

function tryWriteStorage(key: string, entries: string[]): void {
  try {
    localStorage.setItem(key, JSON.stringify(entries));
  } catch {
    // Graceful degradation — localStorage unavailable or quota exceeded.
  }
}

export class ChatHistory {
  private readonly projectId: string;
  private readonly persist: boolean;
  /** In-memory store used both when persist=false and as a fallback. */
  private memory: string[] = [];
  /** Whether localStorage is actually available (lazy-checked on first write). */
  private storageAvailable: boolean | null = null;

  /**
   * @param projectId  Scopes the localStorage key to the active project.
   * @param persist    When false, never writes to localStorage.
   */
  constructor(projectId: string, persist: boolean = true) {
    this.projectId = projectId;
    this.persist = persist;

    if (persist) {
      this.memory = this._load();
    }
  }

  // ── Internal helpers ───────────────────────────────────────────────────────

  private _checkStorageAvailable(): boolean {
    if (this.storageAvailable !== null) return this.storageAvailable;
    try {
      const probe = '__kagan_probe__';
      localStorage.setItem(probe, '1');
      localStorage.removeItem(probe);
      this.storageAvailable = true;
    } catch {
      this.storageAvailable = false;
    }
    return this.storageAvailable;
  }

  private _load(): string[] {
    if (!this._checkStorageAvailable()) return [];
    return tryReadStorage(storageKey(this.projectId));
  }

  private _save(): void {
    if (!this.persist) return;
    if (!this._checkStorageAvailable()) return;
    tryWriteStorage(storageKey(this.projectId), this.memory);
  }

  // ── Public API ─────────────────────────────────────────────────────────────

  /**
   * Returns the current history entries (oldest first, newest last).
   * Reads from localStorage on each call when persist=true so that multiple
   * instances share the same data.
   */
  getEntries(): string[] {
    if (this.persist && this._checkStorageAvailable()) {
      this.memory = tryReadStorage(storageKey(this.projectId));
    }
    return [...this.memory];
  }

  /**
   * Appends an entry to the history, deduplicating consecutive identical
   * entries and trimming to MAX_ENTRIES.
   *
   * Does NOT clear the cursor — callers should reset it after submission.
   */
  push(entry: string): void {
    const trimmed = entry.trim();
    if (!trimmed) return;

    if (this.persist && this._checkStorageAvailable()) {
      this.memory = tryReadStorage(storageKey(this.projectId));
    }

    const last = this.memory.at(-1);
    if (last === trimmed) return;

    this.memory.push(trimmed);
    if (this.memory.length > MAX_ENTRIES) {
      this.memory = this.memory.slice(this.memory.length - MAX_ENTRIES);
    }

    this._save();
  }
}

// ── Cursor ─────────────────────────────────────────────────────────────────

/**
 * Stateful cursor for navigating history with Up/Down arrows.
 *
 * The cursor sits one position AFTER the last entry at rest (i.e. pointing at
 * the "new input" slot). Pressing Up moves backward; pressing Down moves
 * forward. The working draft typed before the first Up press is preserved and
 * restored when the cursor returns to the new-input slot.
 */
export class HistoryCursor {
  private index: number | null = null;
  private draft: string = '';

  reset(): void {
    this.index = null;
    this.draft = '';
  }

  /**
   * Move backward (Up arrow). Returns the entry to display, or null if
   * there is no history to navigate.
   *
   * @param currentText  The text currently in the input — saved as draft on
   *                     the first Up press.
   * @param entries      Full history array (oldest-first).
   */
  up(currentText: string, entries: string[]): string | null {
    if (entries.length === 0) return null;

    if (this.index === null) {
      // First Up — save what the user had typed as a working draft.
      this.draft = currentText;
      this.index = entries.length - 1;
    } else if (this.index > 0) {
      this.index -= 1;
    }

    return entries[this.index] ?? null;
  }

  /**
   * Move forward (Down arrow). Returns the entry to display, or the saved
   * working draft when the cursor returns to the new-input slot (in which case
   * the cursor is reset). Returns null if already at the new-input slot.
   *
   * @param entries  Full history array (oldest-first).
   */
  down(entries: string[]): string | null {
    if (this.index === null) return null;

    if (this.index < entries.length - 1) {
      this.index += 1;
      return entries[this.index] ?? null;
    }

    // Back to new-input slot — restore draft.
    const saved = this.draft;
    this.reset();
    return saved;
  }
}
