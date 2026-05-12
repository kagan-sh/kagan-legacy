export const SESSION_PREFIXES = { orch: 'orch:', gen: 'gen:', task: 'task:' } as const;

export function scopedSessionId(prefix: keyof typeof SESSION_PREFIXES, rawId: string): string {
  return SESSION_PREFIXES[prefix] + rawId;
}

export function parseScopedSessionId(scopedId: string): { prefix: string; rawId: string } | null {
  for (const [key, marker] of Object.entries(SESSION_PREFIXES)) {
    if (scopedId.startsWith(marker)) {
      return { prefix: key, rawId: scopedId.slice(marker.length) };
    }
  }
  return null;
}
