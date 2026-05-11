export async function* parseSSEFrames<T>(
  reader: ReadableStreamDefaultReader<Uint8Array>,
): AsyncGenerator<T> {
  const decoder = new TextDecoder();
  let buffer = '';

  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      buffer += decoder.decode(value, { stream: true });
      const parts = buffer.split('\n\n');
      buffer = parts.pop()!;
      for (const part of parts) {
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
