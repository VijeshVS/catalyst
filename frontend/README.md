# Catalyst frontend

The Catalyst control plane is a React 19 + Vite + TypeScript application using React Router v6 and the Retro Black & Gold design system.

## Commands

```bash
npm install
npm run dev       # Vite dev server on :5173
npm run test      # routing and auth-aware API tests
npm run lint      # Oxlint
npm run build     # TypeScript check + production build
```

## Structure

- `src/pages/` contains the public landing/auth pages and the organization/project workspace routes.
- `src/components/` contains the persistent shell, sidebar, flag controls, environment UI, and creation panel.
- `src/auth/AuthContext.tsx` owns session restoration and protected/public route guards.
- `src/workspace/WorkspaceContext.tsx` owns organization/project summaries and the last-valid organization.
- `src/workspace/useProject.ts` owns project flags, environments, polling, and mutations.
- `src/api.ts` is the typed bearer-token API client. Access tokens stay in memory; the refresh token uses `localStorage` for this MVP and is refreshed automatically after a protected `401`.

The Vite dev server proxies `/api` and `/healthz` to the FastAPI service on port 8000.
