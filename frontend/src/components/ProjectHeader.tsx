import { Link, useLocation, useNavigate } from 'react-router-dom';

import type { Organization, Project } from '../api';
import type { ProjectData } from '../workspace/useProject';

interface ProjectHeaderProps {
  organization: Organization;
  project: Project;
  projectData: ProjectData;
}

function withEnvironment(pathname: string, search: string, environment: string): string {
  const params = new URLSearchParams(search);
  params.set('env', environment);
  return `${pathname}?${params.toString()}`;
}

export function ProjectHeader({ organization, project, projectData }: ProjectHeaderProps) {
  const location = useLocation();
  const navigate = useNavigate();
  const basePath = `/app/orgs/${organization.id}/projects/${project.id}`;
  const currentPath = location.pathname;
  const query = location.search;
  const isFlags = currentPath === basePath;
  const isEnvironments = currentPath === `${basePath}/environments`;
  const isKeys = currentPath === `${basePath}/keys`;
  const isAudit = currentPath === `${basePath}/audit`;
  const isSettings = currentPath === `${basePath}/settings`;

  const navigateEnvironment = (environment: string) => {
    projectData.setActiveEnv(environment);
    navigate(withEnvironment(currentPath, query, environment));
  };

  return (
    <div className="project-header">
      <div className="breadcrumbs">
        <Link to={`/app/orgs/${organization.id}`}>{organization.name}</Link>
        <span aria-hidden="true">/</span>
        <strong>{project.name}</strong>
      </div>
      <div className="project-heading-row">
        <div>
          <span className="eyebrow">Project workspace</span>
          <h1>{project.name}</h1>
          <p>Control flags safely across every environment.</p>
        </div>
        <div className="project-summary-pill">
          <span>{projectData.flags.length}</span> flags
        </div>
      </div>

      <div className="environment-strip" aria-label="Project environments">
        <span className="strip-label">Environment</span>
        <div className="environment-tabs">
          {projectData.environments.map((environment) => (
            <button
              type="button"
              key={environment.id}
              className={`environment-tab ${projectData.activeEnv === environment.name ? 'active' : ''}`}
              onClick={() => navigateEnvironment(environment.name)}
              aria-pressed={projectData.activeEnv === environment.name}
            >
              {environment.name.toUpperCase()}
            </button>
          ))}
          {projectData.environments.length === 0 && <span className="muted-inline">Loading environments…</span>}
        </div>
      </div>

      <nav className="project-tabs" aria-label="Project sections">
        <Link
          to={withEnvironment(basePath, query, projectData.activeEnv)}
          className={`project-tab ${isFlags ? 'active' : ''}`}
        >
          Feature Flags
        </Link>
        <Link
          to={withEnvironment(`${basePath}/environments`, query, projectData.activeEnv)}
          className={`project-tab ${isEnvironments ? 'active' : ''}`}
        >
          Environments
        </Link>
        <Link
          to={withEnvironment(`${basePath}/keys`, query, projectData.activeEnv)}
          className={`project-tab ${isKeys ? 'active' : ''} : ''`}
        >
          API Keys
        </Link>
        <Link
          to={withEnvironment(`${basePath}/audit`, query, projectData.activeEnv)}
          className={`project-tab ${isAudit ? 'active' : ''} disabled-tab`}
          onClick={(event) => event.preventDefault()}
        >
          Audit Log <small>Phase 3</small>
        </Link>
        <Link
          to={withEnvironment(`${basePath}/settings`, query, projectData.activeEnv)}
          className={`project-tab ${isSettings ? 'active' : ''} disabled-tab`}
          onClick={(event) => event.preventDefault()}
        >
          Settings <small>Phase 3</small>
        </Link>
      </nav>
    </div>
  );
}
