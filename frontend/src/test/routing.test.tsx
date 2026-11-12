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
    // The published distribution name must appear in the install snippet, so a
    // rename cannot silently leave stale install instructions on the page.
    const installBlock = document.querySelectorAll('.code-block-body code');
    const installText = [...installBlock].map((el) => el.textContent ?? '').join('\n');
    expect(installText).toContain('pip install sdk-catalyst');
    expect(installText).not.toContain('pip install catalyst-sdk\n');
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

  it('explains the problem, objectives, architecture, and evaluation order', async () => {
    renderAt('/');

    expect(await screen.findByRole('heading', { name: /one deploy/i })).toBeInTheDocument();
    for (const title of [
      'Immediate user exposure',
      'Deployment-dependent rollbacks',
      'No gradual rollout',
      'No emergency kill switch',
    ]) {
      expect(screen.getByRole('heading', { name: title })).toBeInTheDocument();
    }

    expect(screen.getByRole('heading', { name: /what the system/i })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Deterministic sticky rollouts' })).toBeInTheDocument();

    // Both planes and the snapshot fetch path must be named on the page.
    expect(screen.getByRole('heading', { name: /two planes/i })).toBeInTheDocument();
    expect(screen.getByText('Control plane')).toBeInTheDocument();
    expect(screen.getByText('Data plane')).toBeInTheDocument();
    expect(screen.getByText('GET /bootstrap')).toBeInTheDocument();

    // The landing page must document every evaluation reason code.
    for (const reason of [
      'KILL_SWITCH_ACTIVE',
      'ENABLE_ALL_USERS',
      'DEFAULT_VALUE',
      'RULE_AND_ROLLOUT',
      'RULE_OUTSIDE_ROLLOUT',
      'PERCENTAGE_ROLLOUT',
      'PERCENTAGE_OUTSIDE_ROLLOUT',
    ]) {
      expect(screen.getAllByText(reason).length).toBeGreaterThan(0);
    }
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
