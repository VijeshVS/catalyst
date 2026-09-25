import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  clearAuthTokens,
  fetchMe,
  getAccessToken,
  login,
  setAuthTokens,
} from '../api';

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

afterEach(() => {
  clearAuthTokens();
  vi.unstubAllGlobals();
});

describe('auth-aware API client', () => {
  it('stores the token pair returned by JSON login', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => response({
      access_token: 'access-token',
      refresh_token: 'refresh-token',
      token_type: 'bearer',
      user: {
        id: 'user-1',
        email: 'owner@example.com',
        full_name: 'Owner',
        created_at: '2026-01-01T00:00:00Z',
      },
    })));

    await login({ email: 'owner@example.com', password: 'password' });

    expect(getAccessToken()).toBe('access-token');
    expect(fetch).toHaveBeenCalledWith(
      '/api/v1/auth/login',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('refreshes once and retries a protected request after a 401', async () => {
    const user = {
      id: 'user-1',
      email: 'owner@example.com',
      full_name: 'Owner',
      created_at: '2026-01-01T00:00:00Z',
    };
    let meCalls = 0;
    let refreshCalls = 0;
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/auth/refresh')) {
        refreshCalls += 1;
        return response({ access_token: 'fresh-access', refresh_token: 'fresh-refresh' });
      }
      if (url.endsWith('/auth/me')) {
        meCalls += 1;
        return meCalls === 1 ? response({ detail: 'expired' }, 401) : response(user);
      }
      return response({ detail: 'not mocked' }, 404);
    }));
    setAuthTokens({ access_token: 'expired-access', refresh_token: 'stored-refresh' });

    await expect(fetchMe()).resolves.toEqual(user);
    expect(meCalls).toBe(2);
    expect(refreshCalls).toBe(1);
    expect(getAccessToken()).toBe('fresh-access');
  });
});
