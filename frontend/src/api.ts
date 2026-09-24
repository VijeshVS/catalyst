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
  environments: Environment[];
}

export interface Organization {
  id: string;
  name: string;
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

export interface TargetingRule {
  id?: string;
  env: string;
  priority: number;
  conditions_json: any[];
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

const API_BASE = '/api/v1';

async function errorMessage(res: Response, fallback: string): Promise<string> {
  try {
    const body = await res.json();
    if (typeof body?.detail === 'string') return body.detail;
  } catch {
    // Ignore malformed error bodies and fall back to the default message.
  }
  return fallback;
}

async function jsonRequest<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, init);
  if (!res.ok) throw new Error(await errorMessage(res, 'Request failed'));
  return res.json();
}

// ---------------------------------------------------------------------------
// Workspace: organizations, projects & environments
// ---------------------------------------------------------------------------

export async function fetchOrganizations(): Promise<Organization[]> {
  return jsonRequest<Organization[]>(`${API_BASE}/organizations`);
}

export async function createOrganization(name: string): Promise<Organization> {
  return jsonRequest<Organization>(`${API_BASE}/organizations`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
}

export async function createProject(orgId: string, name: string): Promise<Project> {
  return jsonRequest<Project>(`${API_BASE}/organizations/${orgId}/projects`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
}

export async function fetchProjectEnvironments(projectId: string): Promise<Environment[]> {
  return jsonRequest<Environment[]>(
    `${API_BASE}/projects/${projectId}/environments`
  );
}

export async function createEnvironment(projectId: string, name: string): Promise<Environment> {
  return jsonRequest<Environment>(`${API_BASE}/projects/${projectId}/environments`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ name }),
  });
}

// ---------------------------------------------------------------------------
// Health
// ---------------------------------------------------------------------------

export async function fetchHealth(): Promise<HealthStatus> {
  return jsonRequest<HealthStatus>('/healthz');
}

// ---------------------------------------------------------------------------
// Flags (strictly scoped by project_id)
// ---------------------------------------------------------------------------

export async function fetchFlags(projectId: string): Promise<Flag[]> {
  return jsonRequest<Flag[]>(
    `${API_BASE}/flags?project_id=${encodeURIComponent(projectId)}`
  );
}

export async function createFlag(
  projectId: string,
  data: {
    key: string;
    name: string;
    description?: string;
    default_value: boolean;
  }
): Promise<Flag> {
  return jsonRequest<Flag>(
    `${API_BASE}/flags?project_id=${encodeURIComponent(projectId)}`,
    {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }
  );
}

export async function updateFlagEnvState(
  projectId: string,
  flagKey: string,
  env: string,
  data: { enabled?: boolean; percentage?: number }
): Promise<FlagState> {
  return jsonRequest<FlagState>(
    `${API_BASE}/flags/${flagKey}/environments/${env}?project_id=${encodeURIComponent(projectId)}`,
    {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }
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
  attributes?: Record<string, any>;
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
          attributes: data.attributes || {},
        },
      }),
    }
  );
}

// ---------------------------------------------------------------------------
// Audit log
// ---------------------------------------------------------------------------

export async function fetchAuditLogs(projectId: string): Promise<any[]> {
  return jsonRequest<any[]>(
    `${API_BASE}/audit?project_id=${encodeURIComponent(projectId)}`
  );
}
