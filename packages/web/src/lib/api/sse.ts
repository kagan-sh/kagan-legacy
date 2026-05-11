/**
 * SSE parser — fetch + ReadableStream → AsyncGenerator.
 *
 * Supports POST (unlike native EventSource), custom headers, and AbortController.
 * No external dependencies — just standard browser APIs.
 */

import { apiClient } from '@/lib/api/client';
import { parseSSEFrames } from '@/lib/api/sse-parser';

export async function* streamSSE<T>(
  path: string,
  options?: RequestInit,
): AsyncGenerator<T> {
  const url = apiClient.getFullUrl(path);
  const response = await apiClient.streamRequest(url, {
    ...options,
    headers: {
      ...options?.headers,
      Accept: 'text/event-stream',
    },
  });

  if (!response.ok) {
    throw new Error(`SSE request failed: ${response.status} ${response.statusText}`);
  }

  if (!response.body) {
    throw new Error('SSE response has no body');
  }

  const reader = response.body.getReader();
  yield* parseSSEFrames<T>(reader);
}
