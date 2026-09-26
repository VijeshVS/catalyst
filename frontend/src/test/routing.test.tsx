import { render, screen } from '@testing-library/react';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { MemoryRouter } from 'react-router-dom';

import App from '../App';
import { clearAuthTokens, setAuthTokens } from '../api';
import { AuthProvider } from '../auth/AuthContext';

function renderAt(path: string) {
  return render(
    <MemoryRouter
      initialEntries={[path]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <AuthProvider>
        <App />
      </AuthProvider>
    </MemoryRouter>,
  );
}

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

describe('public and protected routing', () => {
  it('renders the public landing page at the root', async () => {
    renderAt('/');
    expect(await screen.findByRole('heading', { name: /ship features with confidence/i })).toBeInTheDocument();
    expect(screen.getByRole('link', { name: /get started/i })).toHaveAttribute('href', '/app');
    expect(screen.getByText('Feature Flags')).toBeInTheDocument();
    expect(screen.getByText('FastAPI')).toBeInTheDocument();
  });

  it('serves the SDK documentation at /docs without authentication', async () => {
    renderAt('/docs');
    expect(
      await screen.findByRole('heading', { name: /evaluated \s*locally/i }),
    ).toBeInTheDocument();
    expect(screen.getByText('catalyst-sdk')).toBeInTheDocument();
    // Every section the table of contents advertises must exist.
    for (const label of [
      'Quick start',
      'Configuration',
      'Evaluation precedence',
      'Operators',
      'API reference',
      'Error handling',
    ]) {
      expect(screen.getByRole('heading', { name: label, level: 2 })).toBeInTheDocument();
    }
    expect(screen.getByRole('link', { name: 'Install' }).getAttribute('href')).toBe('#install');
  });

  it('the landing page CTA points at a route that exists', async () => {
    renderAt('/');
    const cta = await screen.findByRole('link', { name: /view docs/i });
    expect(cta).toHaveAttribute('href', '/docs');
  });

  it('redirects an unauthenticated deep link to login', async () => {
    renderAt('/app/orgs/org-1/projects/project-1/environments');
    expect(await screen.findByRole('heading', { name: /return to your control room/i })).toBeInTheDocument();
    expect(screen.getByLabelText('Email address')).toBeInTheDocument();
  });

  it('restores a session and renders the organization dashboard', async () => {
    const user = {
      id: 'user-1',
      email: 'owner@example.com',
      full_name: 'Workspace Owner',
      created_at: '2026-01-01T00:00:00Z',
    };
    const organization = {
      id: 'org-1',
      name: 'Acme Labs',
      description: 'A private workspace',
      owner_id: 'user-1',
      created_at: '2026-01-01T00:00:00Z',
      projects: [],
    };
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/auth/refresh')) {
        return response({ access_token: 'new-access', refresh_token: 'new-refresh', user });
      }
      if (url.endsWith('/auth/me')) return response(user);
      if (url.endsWith('/organizations')) return response([organization]);
      if (url.endsWith('/healthz')) {
        return response({ status: 'ok', environment: 'test', database: 'ok', redis: 'ok', version: '0.1.0' });
      }
      return response({ detail: 'not mocked' }, 404);
    }));
    setAuthTokens({ access_token: 'old-access', refresh_token: 'stored-refresh' });

    renderAt('/app/orgs/org-1');
    expect(await screen.findByRole('heading', { name: 'Acme Labs' })).toBeInTheDocument();
    expect(screen.getByText('A private workspace')).toBeInTheDocument();
  });

  it('exposes the SDK docs from the authenticated sidebar', async () => {
    const user = {
      id: 'user-1',
      email: 'owner@example.com',
      full_name: 'Workspace Owner',
      created_at: '2026-01-01T00:00:00Z',
    };
    const organization = {
      id: 'org-1',
      name: 'Acme Labs',
      description: null,
      owner_id: 'user-1',
      created_at: '2026-01-01T00:00:00Z',
      projects: [],
    };
    vi.stubGlobal('fetch', vi.fn(async (input: RequestInfo | URL) => {
      const url = String(input);
      if (url.endsWith('/auth/refresh')) {
        return response({ access_token: 'new-access', refresh_token: 'new-refresh', user });
      }
      if (url.endsWith('/auth/me')) return response(user);
      if (url.endsWith('/organizations')) return response([organization]);
      if (url.endsWith('/healthz')) {
        return response({ status: 'ok', environment: 'test', database: 'ok', redis: 'ok', version: '0.1.0' });
      }
      return response({ detail: 'not mocked' }, 404);
    }));
    setAuthTokens({ access_token: 'old-access', refresh_token: 'stored-refresh' });

    renderAt('/app/orgs/org-1');
    // The sidebar renders on every /app/** route, so docs are one click away
    // from anywhere inside the dashboard.
    const docsLink = await screen.findByRole('link', { name: /documentation/i });
    expect(docsLink).toHaveAttribute('href', '/docs');
  });
});
