import { useEffect } from 'react';
import { Link, useParams } from 'react-router-dom';

import { ProjectCard } from '../components/ProjectCard';
import { useWorkspace } from '../workspace/WorkspaceContext';

export function OrgDashboard() {
  const { orgId } = useParams();
  const { getOrganization, selectOrganization, loading, error } = useWorkspace();
  const organization = getOrganization(orgId);

  useEffect(() => {
    if (orgId && organization) selectOrganization(orgId);
  }, [organization, orgId, selectOrganization]);

  if (loading && !organization) return <div className="page-loading">Loading organization…</div>;
  if (error && !organization) return <div className="error-banner">{error}</div>;
  if (!organization) {
    return (
      <div className="not-found-card">
        <span className="eyebrow">404 · Workspace</span>
        <h1>Organization not found.</h1>
        <p>It may have been removed, or this account may not have access.</p>
        <Link className="btn-primary" to="/app">Back to workspace</Link>
      </div>
    );
  }

  const projectCount = organization.projects.length;
  const flagCount = organization.projects.reduce((total, project) => total + (project.flag_count ?? 0), 0);
  const environmentCount = organization.projects.reduce((total, project) => total + (project.environments?.length ?? 0), 0);

  return (
    <div className="workspace-page org-dashboard-page">
      <div className="page-heading-row">
        <div>
          <span className="eyebrow">Organization dashboard</span>
          <h1>{organization.name}</h1>
          <p>{organization.description || 'A focused home for your products, environments, and release decisions.'}</p>
        </div>
        <Link className="btn-primary" to={`/app/orgs/${organization.id}/projects/new`}>
          <span aria-hidden="true">+</span> New project
        </Link>
      </div>

      <div className="org-overview-grid">
        <div className="overview-card"><span className="stat-label">Projects</span><strong>{projectCount}</strong><small>first-class workspaces</small></div>
        <div className="overview-card"><span className="stat-label">Feature flags</span><strong>{flagCount}</strong><small>across this organization</small></div>
        <div className="overview-card"><span className="stat-label">Environments</span><strong>{environmentCount}</strong><small>isolated release lanes</small></div>
      </div>

      <div className="section-heading-row">
        <div><span className="eyebrow">Your projects</span><h2>Ship something meaningful.</h2></div>
        <span className="section-count">{projectCount} {projectCount === 1 ? 'project' : 'projects'}</span>
      </div>

      {projectCount === 0 ? (
        <div className="empty-state workspace-empty-state">
          <div className="empty-illustration" aria-hidden="true"><span>✦</span><i /><i /><i /></div>
          <h2>Create your first project</h2>
          <p>Projects get isolated flags and the standard <strong>dev</strong>, <strong>staging</strong>, and <strong>prod</strong> environments automatically.</p>
          <Link className="btn-primary" to={`/app/orgs/${organization.id}/projects/new`}>Create your first project <span aria-hidden="true">→</span></Link>
        </div>
      ) : (
        <div className="project-grid">
          {organization.projects.map((project) => <ProjectCard key={project.id} organizationId={organization.id} project={project} />)}
        </div>
      )}
    </div>
  );
}
