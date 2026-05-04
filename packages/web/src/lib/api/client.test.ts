import { afterEach, describe, expect, it, vi } from 'vitest';
import { KaganApiClient } from './client';

describe('KaganApiClient web URL handling', () => {
  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('uses same-origin health URL before bundled mode is configured', async () => {
    const fetchMock = vi.spyOn(globalThis, 'fetch').mockResolvedValue(
      new Response(JSON.stringify({ status: 'ok', version: 'test' }), {
        status: 200,
        headers: { 'content-type': 'application/json' },
      }),
    );
    const client = new KaganApiClient();

    await expect(client.getHealth()).resolves.toEqual({ status: 'ok', version: 'test' });

    expect(fetchMock).toHaveBeenCalledWith('/health', {
      headers: { Accept: 'application/json' },
    });
    expect(client.getBaseUrl()).toBe('');
  });
});
