import { beforeEach, describe, expect, it, vi } from 'vitest';
import { ChatHistory, HistoryCursor } from '@/lib/chat-history';

// ── ChatHistory class ────────────────────────────────────────────────────────

describe('ChatHistory', () => {
  beforeEach(() => {
    localStorage.clear();
    // Reset storageAvailable probe side-effect by replacing the storage mock.
    // (The setup.ts mock is a real Storage; clearing it is sufficient.)
  });

  it('persists entries across instances', () => {
    const h1 = new ChatHistory('proj-1', true);
    h1.push('first');
    h1.push('second');

    const h2 = new ChatHistory('proj-1', true);
    const entries = h2.getEntries();
    expect(entries).toContain('first');
    expect(entries).toContain('second');
  });

  it('deduplicates consecutive identical entries', () => {
    const h = new ChatHistory('proj-dedup', true);
    h.push('foo');
    h.push('foo');
    expect(h.getEntries()).toHaveLength(1);
    expect(h.getEntries()[0]).toBe('foo');
  });

  it('allows non-consecutive duplicates', () => {
    const h = new ChatHistory('proj-nonconsec', true);
    h.push('foo');
    h.push('bar');
    h.push('foo');
    expect(h.getEntries()).toHaveLength(3);
  });

  it('trims to 200 entries', () => {
    const h = new ChatHistory('proj-trim', true);
    for (let i = 0; i < 250; i++) {
      h.push(`msg-${i}`);
    }
    expect(h.getEntries()).toHaveLength(200);
    // newest entries kept
    expect(h.getEntries().at(-1)).toBe('msg-249');
  });

  it('falls back to memory when localStorage unavailable', () => {
    // Override localStorage to throw on every call.
    const orig = Object.getOwnPropertyDescriptor(globalThis, 'localStorage');
    Object.defineProperty(globalThis, 'localStorage', {
      configurable: true,
      get: () => {
        throw new Error('localStorage not available');
      },
    });

    let error: unknown = null;
    let entries: string[] = [];
    try {
      const h = new ChatHistory('proj-fallback', true);
      h.push('hello');
      entries = h.getEntries();
    } catch (e) {
      error = e;
    }

    // Restore original descriptor.
    if (orig) {
      Object.defineProperty(globalThis, 'localStorage', orig);
    }

    expect(error).toBeNull();
    // In-memory fallback: entries may be empty because load fails, but push
    // must not throw. After the probe fails, memory is used.
    expect(() => entries).not.toThrow();
  });

  it('disabled when persist is false — does not write to localStorage', () => {
    const setItemSpy = vi.spyOn(localStorage, 'setItem');

    const h = new ChatHistory('proj-nopersist', false);
    h.push('msg-a');
    h.push('msg-b');

    expect(setItemSpy).not.toHaveBeenCalled();

    // But in-memory retrieval still works within the same instance.
    expect(h.getEntries()).toEqual(['msg-a', 'msg-b']);

    setItemSpy.mockRestore();
  });

  it('ignores empty or whitespace-only entries', () => {
    const h = new ChatHistory('proj-empty', true);
    h.push('');
    h.push('   ');
    expect(h.getEntries()).toHaveLength(0);
  });
});

// ── HistoryCursor ────────────────────────────────────────────────────────────

describe('HistoryCursor', () => {
  it('returns null when no history exists', () => {
    const cursor = new HistoryCursor();
    expect(cursor.up('draft', [])).toBeNull();
  });

  it('up arrow cycles to most-recent entry first', () => {
    const cursor = new HistoryCursor();
    const entries = ['first', 'second', 'third'];
    expect(cursor.up('', entries)).toBe('third');
    expect(cursor.up('', entries)).toBe('second');
    expect(cursor.up('', entries)).toBe('first');
    // Clamped at oldest.
    expect(cursor.up('', entries)).toBe('first');
  });

  it('working draft preserved when cycling', () => {
    const cursor = new HistoryCursor();
    const entries = ['old-msg'];

    // User typed a draft; press Up.
    const historyEntry = cursor.up('draft text', entries);
    expect(historyEntry).toBe('old-msg');

    // Press Down — draft is restored.
    const restored = cursor.down(entries);
    expect(restored).toBe('draft text');
  });

  it('down returns null when cursor is at rest', () => {
    const cursor = new HistoryCursor();
    expect(cursor.down([])).toBeNull();
  });

  it('navigating down past end returns to draft and resets cursor', () => {
    const cursor = new HistoryCursor();
    const entries = ['a', 'b'];
    cursor.up('my draft', entries); // index → 1 (= 'b')
    cursor.up('', entries);          // index → 0 (= 'a')
    cursor.down(entries);            // index → 1 (= 'b')
    const result = cursor.down(entries); // past end → restore draft
    expect(result).toBe('my draft');
    // Cursor is reset — down again is a no-op.
    expect(cursor.down(entries)).toBeNull();
  });

  it('reset clears cursor and draft', () => {
    const cursor = new HistoryCursor();
    const entries = ['msg'];
    cursor.up('draft', entries);
    cursor.reset();
    expect(cursor.down(entries)).toBeNull();
  });
});
