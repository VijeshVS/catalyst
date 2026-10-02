import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';

import type { Organization, Project } from '../api';
import { copyText } from '../lib/clipboard';
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
  const [copied, setCopied] = useState(false);
  const basePath = `/app/orgs/${organization.id}/projects/${project.id}`;
  const currentPath = location.pathname;
  const query = location.search;
  const isFlags = currentPath === basePath;
  const isEnvironments = currentPath === `${basePath}/environments`;
  const isKeys = currentPath === `${basePath}/keys`;

  const navigateEnvironment = (environment: string) => {
    projectData.setActiveEnv(environment);
    navigate(withEnvironment(currentPath, query, environment));
  };

  // The SDK needs this value alongside an SDK key, so make it copyable rather
  // than forcing anyone to select a UUID by hand.
  const copyProjectId = async () => {
    // Clipboard access can be denied; do not claim a copy happened.
    if (!(await copyText(project.id))) return;
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
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

      <div className="project-id-row">
        <span className="project-id-label" id="project-id-label">
          Project ID
        </span>
        <code className="project-id-value">{project.id}</code>
        <button
          type="button"
          className="project-id-copy"
          onClick={copyProjectId}
          aria-labelledby="project-id-label"
          data-copied={copied}
        >
          {copied ? 'Copied' : 'Copy'}
        </button>
        <span className="project-id-hint">
          Used by the SDK alongside your API key.
        </span>
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
          className={`project-tab ${isKeys ? 'active' : ''}`}
        >
          API Keys
        </Link>
      </nav>
    </div>
  );
}
