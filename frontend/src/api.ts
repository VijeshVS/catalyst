export interface User {
  id: string;
  email: string;
  full_name: string;
  created_at: string;
}

export interface TokenPair {
  access_token: string;
  refresh_token: string;
  token_type?: string;
}

export interface AuthResponse extends TokenPair {
  user: User;
}

export interface Environment {
  id: string;
  project_id: string;
  name: string;
  version: number;
}

export interface Project {
  id: string;
  org_id: string;
  name: string;
  created_at: string;
  updated_at?: string | null;
  environments: Environment[];
  flag_count?: number;
}

export interface Organization {
  id: string;
  name: string;
  description?: string | null;
  owner_id: string;
  created_at: string;
  projects: Project[];
}

export interface FlagState {
  id?: string;
  env: string;
  enabled: boolean;
  percentage: number;
  version: number;
}

/**
 * Canonical condition operators accepted by the API. Aliases (`eq`, `gt`, …)
 * are normalized server-side; the builder always sends canonical names.
 */
export type RuleOperator =
  | 'equals'
  | 'not_equals'
  | 'in'
  | 'not_in'
  | 'contains'
  | 'starts_with'
  | 'ends_with'
  | 'greater_than'
  | 'greater_than_or_equal'
  | 'less_than'
  | 'less_than_or_equal'
  | 'exists'
  | 'not_exists';

export interface RuleCondition {
  attr: string;
  op: RuleOperator;
  value?: unknown;
}

export interface TargetingRule {
  id: string;
  env: string;
  priority: number;
  conditions: RuleCondition[];
  serve: boolean;
}

export interface Flag {
  id: string;
  project_id: string;
  key: string;
  name: string;
  description?: string;
  default_value: boolean;
  archived: boolean;
  created_at: string;
  states: FlagState[];
  rules: TargetingRule[];
}

export interface HealthStatus {
  status: string;
  environment: string;
  database: string;
  redis: string;
  version: string;
}

export interface EvaluateResult {
  flag_key: string;
  value: boolean;
  reason: string;
  rule_id?: string;
}

export interface AuditLog {
  id: string;
  flag_id?: string | null;
  env?: string | null;
  actor: string;
  user_id?: string | null;
  user_email?: string | null;
  action: string;
  before?: unknown;
  after?: unknown;
  created_at: string;
}

/**
 * Base URL for the API.
 *
 * Defaults to the relative `/api/v1`, which the Vite dev server proxies to a
 * local backend. When the frontend is deployed separately from the API (for
 * example Vercel in front of a Render web service), set `VITE_API_BASE_URL` to
 * the backend's absolute origin, e.g. `https://catalyst-api-uakz.onrender.com/api/v1`.
 */
const API_BASE = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '');

/** Health lives at the API root rather than under the versioned prefix. */
const HEALTH_URL = import.meta.env.VITE_API_HEALTH_URL || '/healthz';

const REFRESH_TOKEN_KEY = 'catalyst.refreshToken';

let accessToken: string | null = null;
let refreshToken: string | null = readRefreshToken();
let refreshInFlight: Promise<string | null> | null = null;
let authExpiredHandler: (() => void) | null = null;

export class ApiError extends Error {
  readonly status: number;

  constructor(message: string, status: number) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

function readRefreshToken(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage.getItem(REFRESH_TOKEN_KEY);
  } catch {
    return null;
  }
}

function writeRefreshToken(token: string | null): void {
  if (typeof window === 'undefined') return;
  try {
    if (token) {
      window.localStorage.setItem(REFRESH_TOKEN_KEY, token);
    } else {
      window.localStorage.removeItem(REFRESH_TOKEN_KEY);
    }
  } catch {
    // Private browsing modes can deny localStorage. The in-memory access token
    // remains usable for the current tab.
  }
}

export function setAuthTokens(tokens: TokenPair): void {
  accessToken = tokens.access_token;
  refreshToken = tokens.refresh_token;
  writeRefreshToken(tokens.refresh_token);
}

export function clearAuthTokens(): void {
  accessToken = null;
  refreshToken = null;
  writeRefreshToken(null);
}

export function getAccessToken(): string | null {
  return accessToken;
}

export function getRefreshToken(): string | null {
  return refreshToken;
}

export function hasRefreshToken(): boolean {
  return refreshToken !== null;
}

export function onAuthExpired(handler: (() => void) | null): void {
  authExpiredHandler = handler;
}

function notifyAuthExpired(): void {
  authExpiredHandler?.();
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null;
}

async function responseMessage(response: Response, fallback: string): Promise<string> {
  try {
    const body: unknown = await response.json();
    if (isRecord(body) && typeof body.detail === 'string') return body.detail;
    if (isRecord(body) && Array.isArray(body.detail)) {
      const first = body.detail[0];
      if (isRecord(first) && typeof first.msg === 'string') return first.msg;
    }
  } catch {
    // A proxy may return an empty/non-JSON error body.
  }
  return fallback;
}

async function refreshAccessToken(): Promise<string | null> {
  if (!refreshToken) return null;
  if (refreshInFlight) return refreshInFlight;

  refreshInFlight = (async () => {
    const token = refreshToken;
    if (!token) return null;

    try {
      const response = await fetch(`${API_BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: token }),
      });
      if (!response.ok) {
        clearAuthTokens();
        return null;
      }
      const body: unknown = await response.json();
      if (!isRecord(body) || typeof body.access_token !== 'string' || typeof body.refresh_token !== 'string') {
        clearAuthTokens();
        return null;
      }
      setAuthTokens({ access_token: body.access_token, refresh_token: body.refresh_token });
      return body.access_token;
    } catch {
      clearAuthTokens();
      return null;
    } finally {
      refreshInFlight = null;
    }
  })();

  return refreshInFlight;
}

interface RequestOptions {
  skipAuthRefresh?: boolean;
}

async function jsonRequest<T>(
  path: string,
  init: RequestInit = {},
  options: RequestOptions = {},
): Promise<T> {
  const request = async (retry: boolean): Promise<Response> => {
    const headers = new Headers(init.headers);
    if (accessToken && !headers.has('Authorization')) {
      headers.set('Authorization', `Bearer ${accessToken}`);
    }

    const response = await fetch(path, { ...init, headers });
    if (
      response.status === 401 &&
      retry &&
      !options.skipAuthRefresh &&
      !path.includes('/auth/login') &&
      !path.includes('/auth/register') &&
      !path.includes('/auth/refresh')
    ) {
      const refreshed = await refreshAccessToken();
      if (refreshed) return request(false);
      clearAuthTokens();
      notifyAuthExpired();
    }
    if (response.status === 401 && !options.skipAuthRefresh && !retry) {
      clearAuthTokens();
      notifyAuthExpired();
    }
    return response;
  };

  const response = await request(true);
  if (!response.ok) {
    throw new ApiError(
      await responseMessage(response, response.status === 401 ? 'Authentication required' : 'Request failed'),
      response.status,
    );
  }
  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

export function getErrorMessage(error: unknown, fallback = 'Something went wrong'): string {
  if (error instanceof Error && error.message) return error.message;
  return fallback;
}

// ---------------------------------------------------------------------------
// Authentication
// ---------------------------------------------------------------------------
export async function register(input: {
  email: string;
  password: string;
  full_name: string;
}): Promise<AuthResponse> {
  const response = await jsonRequest<AuthResponse>(
    `${API_BASE}/auth/register`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    },
    { skipAuthRefresh: true },
  );
  setAuthTokens(response);
  return response;
}

export async function login(input: { email: string; password: string }): Promise<AuthResponse> {
  const response = await jsonRequest<AuthResponse>(
    `${API_BASE}/auth/login`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(input),
    },
    { skipAuthRefresh: true },
  );
  setAuthTokens(response);
  return response;
}

export async function refreshSession(): Promise<AuthResponse | null> {
  const token = await refreshAccessToken();
  if (!token) return null;
  // refreshAccessToken intentionally only returns the access token. The
  // persisted refresh token is still valid, so fetch the profile separately.
  return fetchMe().then((user) => ({
    access_token: token,
    refresh_token: getRefreshToken() ?? '',
    token_type: 'bearer',
    user,
  }));
}

export async function fetchMe(): Promise<User> {
  return jsonRequest<User>(`${API_BASE}/auth/me`);
}

export function logout(): void {
  clearAuthTokens();
}

// ---------------------------------------------------------------------------
// Workspace: organizations, projects & environments
// ---------------------------------------------------------------------------
export async function fetchOrganizations(): Promise<Organization[]> {
  return jsonRequest<Organization[]>(`${API_BASE}/organizations`);
}

export async function createOrganization(name: string, description?: string): Promise<Organization> {
  return jsonRequest<Organization>(`${API_BASE}/organizations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name, description: description?.trim() || undefined }),
  });
}

export async function createProject(orgId: string, name: string): Promise<Project> {
  return jsonRequest<Project>(`${API_BASE}/organizations/${encodeURIComponent(orgId)}/projects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
}

export async function fetchProjectEnvironments(projectId: string): Promise<Environment[]> {
  return jsonRequest<Environment[]>(
    `${API_BASE}/projects/${encodeURIComponent(projectId)}/environments`,
  );
}

export async function createEnvironment(projectId: string, name: string): Promise<Environment> {
  return jsonRequest<Environment>(
    `${API_BASE}/projects/${encodeURIComponent(projectId)}/environments`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ name }),
    },
  );
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------
export async function fetchHealth(): Promise<HealthStatus> {
  return jsonRequest<HealthStatus>(HEALTH_URL, {}, { skipAuthRefresh: true });
}

// ---------------------------------------------------------------------------
// Flags (strictly scoped by project_id)
// ---------------------------------------------------------------------------
export async function fetchFlags(projectId: string): Promise<Flag[]> {
  return jsonRequest<Flag[]>(
    `${API_BASE}/flags?project_id=${encodeURIComponent(projectId)}`,
  );
}

export async function createFlag(
  projectId: string,
  data: {
    key: string;
    name: string;
    description?: string;
    default_value: boolean;
  },
): Promise<Flag> {
  return jsonRequest<Flag>(
    `${API_BASE}/flags?project_id=${encodeURIComponent(projectId)}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    },
  );
}

export async function updateFlagEnvState(
  projectId: string,
  flagKey: string,
  env: string,
  data: { enabled?: boolean; percentage?: number },
): Promise<FlagState> {
  return jsonRequest<FlagState>(
    `${API_BASE}/flags/${encodeURIComponent(flagKey)}/environments/${encodeURIComponent(env)}?project_id=${encodeURIComponent(projectId)}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    },
  );
}

export async function updateFlag(
  projectId: string,
  flagKey: string,
  data: { default_value?: boolean },
): Promise<Flag> {
  return jsonRequest<Flag>(
    `${API_BASE}/flags/${encodeURIComponent(flagKey)}?project_id=${encodeURIComponent(projectId)}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    },
  );
}

// ---------------------------------------------------------------------------
// Targeting rules (environment scoped, ordered by priority)
// ---------------------------------------------------------------------------
function rulesPath(flagKey: string, env: string): string {
  return `${API_BASE}/flags/${encodeURIComponent(flagKey)}/environments/${encodeURIComponent(env)}/rules`;
}

function rulesUrl(projectId: string, flagKey: string, env: string): string {
  return `${rulesPath(flagKey, env)}?project_id=${encodeURIComponent(projectId)}`;
}

export async function fetchFlagRules(
  projectId: string,
  flagKey: string,
  env: string,
): Promise<TargetingRule[]> {
  return jsonRequest<TargetingRule[]>(rulesUrl(projectId, flagKey, env));
}

export async function createFlagRule(
  projectId: string,
  flagKey: string,
  env: string,
  data: { conditions: RuleCondition[]; serve: boolean; priority?: number },
): Promise<TargetingRule> {
  return jsonRequest<TargetingRule>(rulesUrl(projectId, flagKey, env), {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
}

export async function updateFlagRule(
  projectId: string,
  flagKey: string,
  env: string,
  ruleId: string,
  data: { conditions?: RuleCondition[]; serve?: boolean; priority?: number },
): Promise<TargetingRule> {
  return jsonRequest<TargetingRule>(
    `${rulesPath(flagKey, env)}/${encodeURIComponent(ruleId)}?project_id=${encodeURIComponent(projectId)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    },
  );
}

export async function reorderFlagRules(
  projectId: string,
  flagKey: string,
  env: string,
  ruleIds: string[],
): Promise<TargetingRule[]> {
  return jsonRequest<TargetingRule[]>(
    `${rulesPath(flagKey, env)}/reorder?project_id=${encodeURIComponent(projectId)}`,
    {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ rule_ids: ruleIds }),
    },
  );
}

export async function deleteFlagRule(
  projectId: string,
  flagKey: string,
  env: string,
  ruleId: string,
): Promise<void> {
  return jsonRequest<void>(
    `${rulesPath(flagKey, env)}/${encodeURIComponent(ruleId)}?project_id=${encodeURIComponent(projectId)}`,
    { method: 'DELETE' },
  );
}

// ---------------------------------------------------------------------------
// Evaluation
// ---------------------------------------------------------------------------
export async function evaluateFlag(data: {
  projectId: string;
  flag_key: string;
  env: string;
  user_id: string;
  attributes?: Record<string, unknown>;
}): Promise<EvaluateResult> {
  return jsonRequest<EvaluateResult>(
    `${API_BASE}/evaluate?project_id=${encodeURIComponent(data.projectId)}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        flag_key: data.flag_key,
        env: data.env,
        context: {
          user_id: data.user_id,
          attributes: data.attributes ?? {},
        },
      }),
    },
  );
}

// ---------------------------------------------------------------------------
// Audit log
// ---------------------------------------------------------------------------
export async function fetchAuditLogs(projectId: string): Promise<AuditLog[]> {
  return jsonRequest<AuditLog[]>(
    `${API_BASE}/audit?project_id=${encodeURIComponent(projectId)}`,
  );
}

// ---------------------------------------------------------------------------
// API Keys
// ---------------------------------------------------------------------------
export interface ApiKey {
  id: string;
  project_id: string;
  env: string;
  name: string;
  prefix: string;
  revoked: boolean;
  created_at: string;
}

export interface ApiKeyListResponse {
  keys: ApiKey[];
}

export async function createApiKey(
  projectId: string,
  data: { name: string; env: string },
): Promise<ApiKey> {
  return jsonRequest<ApiKey>(
    `${API_BASE}/projects/${encodeURIComponent(projectId)}/keys`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    },
  );
}

export async function fetchApiKeys(projectId: string): Promise<ApiKeyListResponse> {
  return jsonRequest<ApiKeyListResponse>(
    `${API_BASE}/projects/${encodeURIComponent(projectId)}/keys`,
  );
}

export async function revokeApiKey(projectId: string, keyId: string): Promise<void> {
  return jsonRequest<void>(
    `${API_BASE}/projects/${encodeURIComponent(projectId)}/keys/${encodeURIComponent(keyId)}`,
    {
      method: 'DELETE',
    },
  );
}
