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

export async function fetchHealth(): Promise<HealthStatus> {
  const res = await fetch('/healthz');
  if (!res.ok) throw new Error('Failed to fetch health');
  return res.json();
}

export async function fetchFlags(): Promise<Flag[]> {
  const res = await fetch(`${API_BASE}/flags`);
  if (!res.ok) throw new Error('Failed to fetch flags');
  return res.json();
}

export async function createFlag(data: {
  key: string;
  name: string;
  description?: string;
  default_value: boolean;
}): Promise<Flag> {
  const res = await fetch(`${API_BASE}/flags`, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) {
    const err = await res.json();
    throw new Error(err.detail || 'Failed to create flag');
  }
  return res.json();
}

export async function updateFlagEnvState(
  flagKey: string,
  env: string,
  data: { enabled?: boolean; percentage?: number }
): Promise<FlagState> {
  const res = await fetch(`${API_BASE}/flags/${flagKey}/environments/${env}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(data),
  });
  if (!res.ok) throw new Error('Failed to update environment state');
  return res.json();
}

export async function evaluateFlag(data: {
  flag_key: string;
  env: string;
  user_id: string;
  attributes?: Record<string, any>;
}): Promise<EvaluateResult> {
  const res = await fetch(`${API_BASE}/evaluate`, {
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
  });
  if (!res.ok) throw new Error('Failed to evaluate flag');
  return res.json();
}

export async function fetchAuditLogs(): Promise<any[]> {
  const res = await fetch(`${API_BASE}/audit`);
  if (!res.ok) throw new Error('Failed to fetch audit logs');
  return res.json();
}
