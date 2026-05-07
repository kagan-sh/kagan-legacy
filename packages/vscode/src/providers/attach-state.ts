/**
 * Shared attach-state store for the @kagan chat participant.
 *
 * A thin in-memory registry keyed by VS Code chat participant conversation id
 * (or a global sentinel when the panel does not provide one). Stored here so
 * that the running-agents tree-view can trigger an attach without importing
 * the full chat.participant module (which would create a circular dependency
 * through extension.ts).
 */

export interface AttachEntry {
  sessionId: string;
  taskTitle: string;
}

// Global attach state — tracks which session the chat panel is currently
// streaming. Keyed by VS Code chat request conversation id; "global" is used
// as a fallback when the conversation id is unavailable.
const store = new Map<string, AttachEntry>();

export const attachState = {
  get(conversationId: string): AttachEntry | undefined {
    return store.get(conversationId) ?? store.get("global");
  },

  set(conversationId: string, entry: AttachEntry): void {
    store.set(conversationId, entry);
  },

  /** Clear attach state for a conversation (detach). */
  clear(conversationId: string): void {
    store.delete(conversationId);
    // Also clear global if it matches
    const global = store.get("global");
    if (global?.sessionId === store.get(conversationId)?.sessionId) {
      store.delete("global");
    }
  },

  /** Set the global (panel-level) attach entry — used by tree-view click. */
  setGlobal(entry: AttachEntry): void {
    store.set("global", entry);
  },

  clearGlobal(): void {
    store.delete("global");
  },

  /** True if any conversation is currently attached. */
  hasAny(): boolean {
    return store.size > 0;
  },
};
