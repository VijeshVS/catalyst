import { useEffect } from 'react';
import { Outlet, useLocation, useParams } from 'react-router-dom';

import { ProjectHeader } from '../components/ProjectHeader';
import { useWorkspace } from '../workspace/WorkspaceContext';
import { useProject } from '../workspace/useProject';
import type { ProjectOutletContext } from '../workspace/useProject';

export function ProjectLayout() {
  const { orgId, projectId } = useParams();
  const location = useLocation();
  const { getOrganization, selectOrganization, loading: workspaceLoading } = useWorkspace();
  const organization = getOrganization(orgId);
  const project = organization?.projects.find((candidate) => candidate.id === projectId);
  const projectData = useProject(project?.id);
  const { environments, setActiveEnv } = projectData;
  const requestedEnvironment = new URLSearchParams(location.search).get('env');

  useEffect(() => {
    if (orgId && organization) selectOrganization(orgId);
  }, [organization, orgId, selectOrganization]);

  useEffect(() => {
    if (
      requestedEnvironment &&
      environments.some((environment) => environment.name === requestedEnvironment)
    ) {
      setActiveEnv(requestedEnvironment);
    }
  }, [environments, requestedEnvironment, setActiveEnv]);

  if (workspaceLoading && !organization) {
    return <div className="page-loading">Loading project workspace…</div>;
  }

  if (!organization || !project) {
    return (
      <div className="not-found-card">
        <span className="eyebrow">404 · Project</span>
        <h1>Project not found.</h1>
        <p>This project may have moved, or your account may not have access to it.</p>
        <a className="btn-primary" href={`/app/orgs/${orgId ?? ''}`}>Back to organization</a>
      </div>
    );
  }

  const outletContext: ProjectOutletContext = { projectData };

  return (
    <>
      <ProjectHeader organization={organization} project={project} projectData={projectData} />
      <div className="project-content-wrap">
        <Outlet context={outletContext} />
      </div>
    </>
  );
}
