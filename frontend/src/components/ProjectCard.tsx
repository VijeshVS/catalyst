import { Link } from 'react-router-dom';

import type { Project } from '../api';
import { EnvBadge } from './EnvBadge';

interface ProjectCardProps {
  organizationId: string;
  project: Project;
}

function formatDate(value?: string | null): string {
  if (!value) return 'Not updated yet';
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return 'Recently';
  return new Intl.DateTimeFormat(undefined, { month: 'short', day: 'numeric', year: 'numeric' }).format(date);
}

export function ProjectCard({ organizationId, project }: ProjectCardProps) {
  const environments = project.environments ?? [];
  const visibleEnvironments = environments.slice(0, 4);
  const hiddenCount = Math.max(0, environments.length - visibleEnvironments.length);

  return (
    <Link className="project-card" to={`/app/orgs/${organizationId}/projects/${project.id}`}>
      <div className="project-card-top">
        <span className="project-card-icon" aria-hidden="true">◈</span>
        <span className="project-card-arrow" aria-hidden="true">↗</span>
      </div>
      <div className="project-card-name-row">
        <h3>{project.name}</h3>
        <span className="project-card-count">{project.flag_count ?? 0} flag{project.flag_count === 1 ? '' : 's'}</span>
      </div>
      <div className="project-card-environments">
        {visibleEnvironments.map((environment) => <EnvBadge key={environment.id} name={environment.name} compact />)}
        {hiddenCount > 0 && <span className="env-overflow">+{hiddenCount} more</span>}
      </div>
      <div className="project-card-footer">
        <span>Updated {formatDate(project.updated_at ?? project.created_at)}</span>
        <span className="project-card-status"><i /> Active</span>
      </div>
    </Link>
  );
}
