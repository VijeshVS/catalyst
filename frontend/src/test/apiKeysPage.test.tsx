import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { ApiKeysPage } from '../pages/ApiKeysPage';

vi.mock('react-router-dom', () => ({
  useParams: () => ({ projectId: 'project-1' }),
}));

const key = {
  id: 'key-1',
  project_id: 'project-1',
  env: 'prod',
  name: 'Production SDK Key',
  revoked: false,
  created_at: '2026-01-02T00:00:00Z',
};

function response(body: unknown, status = 200): Response {
  return new Response(status === 204 ? null : JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

function stubFetch(keys: unknown[] = [key]) {
  const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
    const url = String(input);
    if (init?.method === 'DELETE') return response(null, 204);
    if (url.endsWith('/projects/project-1/keys')) return response({ keys });
    return response({ detail: 'not mocked' }, 404);
  });
  vi.stubGlobal('fetch', fetchMock);
  return fetchMock;
}

beforeEach(() => {
  vi.spyOn(window, 'confirm').mockReturnValue(true);
});

afterEach(() => {
  vi.unstubAllGlobals();
  vi.restoreAllMocks();
});

describe('API keys page', () => {
  it('offers a delete action for a key', async () => {
    stubFetch();
    render(<ApiKeysPage />);

    expect(await screen.findByRole('heading', { name: key.name })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument();
    // A deleted key leaves no card behind, so no revoked state is ever shown.
    expect(screen.queryByText('Revoked')).not.toBeInTheDocument();
  });

  it('names the key in the confirmation', async () => {
    stubFetch();
    render(<ApiKeysPage />);
    await screen.findByRole('heading', { name: key.name });

    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));

    expect(window.confirm).toHaveBeenCalledWith(
      expect.stringContaining(key.name),
    );
  });

  it('deletes the key and drops it from the list', async () => {
    let keys = [key];
    const fetchMock = vi.fn(async (input: RequestInfo | URL, init?: RequestInit) => {
      if (init?.method === 'DELETE') {
        keys = [];
        return response(null, 204);
      }
      if (String(input).endsWith('/projects/project-1/keys')) return response({ keys });
      return response({ detail: 'not mocked' }, 404);
    });
    vi.stubGlobal('fetch', fetchMock);
    render(<ApiKeysPage />);
    await screen.findByRole('heading', { name: key.name });

    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));

    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/projects/project-1/keys/key-1'),
        expect.objectContaining({ method: 'DELETE' }),
      ),
    );
    expect(await screen.findByText(/no api keys yet/i)).toBeInTheDocument();
    expect(screen.queryByRole('heading', { name: key.name })).not.toBeInTheDocument();
  });

  it('keeps the key when the confirmation is dismissed', async () => {
    vi.spyOn(window, 'confirm').mockReturnValue(false);
    const fetchMock = stubFetch();
    render(<ApiKeysPage />);
    await screen.findByRole('heading', { name: key.name });

    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));

    await waitFor(() => expect(window.confirm).toHaveBeenCalled());
    const deleted = fetchMock.mock.calls.filter(([, init]) => (init as RequestInit)?.method === 'DELETE');
    expect(deleted).toHaveLength(0);
    expect(screen.getByRole('heading', { name: key.name })).toBeInTheDocument();
  });
});
