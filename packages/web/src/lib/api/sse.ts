/**
 * SSE parser — fetch + ReadableStream → AsyncGenerator.
 *
 * Supports POST (unlike native EventSource), custom headers, and AbortController.
 * No external dependencies — just standard browser APIs.
 */

import { apiClient } from '@/lib/api/client';

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

  const reader = response.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += value;
      const parts = buffer.split('\n\n');
      buffer = parts.pop()!;
      for (const part of parts) {
        // Skip comments (keepalive lines starting with :)
        const dataLine = part.split('\n').find((l) => l.startsWith('data: '));
        if (dataLine) {
          yield JSON.parse(dataLine.slice(6)) as T;
        }
      }
    }
  } finally {
    reader.cancel().catch(() => {});
  }
}
