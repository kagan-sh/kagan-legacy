import type { RightRailMode } from '@/lib/atoms/ui';

export type DockedChatRailMode = Extract<RightRailMode, 'chat-right' | 'chat-bottom'>;

/** chat-right → chat-bottom → none (close) */
export function cycleDockMode(mode: DockedChatRailMode): DockedChatRailMode | 'none' {
  if (mode === 'chat-right') return 'chat-bottom';
  return 'none';
}
