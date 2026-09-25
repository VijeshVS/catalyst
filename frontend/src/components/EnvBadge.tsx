const STANDARD_ENVIRONMENTS = new Set(['dev', 'staging', 'prod']);

interface EnvBadgeProps {
  name: string;
  version?: number;
  compact?: boolean;
}

export function EnvBadge({ name, version, compact = false }: EnvBadgeProps) {
  const isStandard = STANDARD_ENVIRONMENTS.has(name);
  return (
    <span className={`env-badge ${isStandard ? 'standard' : 'custom'} ${compact ? 'compact' : ''}`}>
      {name}
      {version !== undefined && <span className="env-version">v{version}</span>}
    </span>
  );
}
