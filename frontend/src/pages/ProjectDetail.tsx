import { useState } from 'react';
import { Link, useParams } from 'react-router-dom';

import { FlagCard } from '../components/FlagCard';
import { FlagCreatePanel } from '../components/FlagCreatePanel';
import { useProjectData } from '../workspace/useProject';
import { useWorkspace } from '../workspace/WorkspaceContext';

export function ProjectDetail() {
  const { orgId, projectId } = useParams();
  const { getOrganization } = useWorkspace();
  const projectData = useProjectData();
  const [panelOpen, setPanelOpen] = useState(false);
  const organization = getOrganization(orgId);
  const project = organization?.projects.find((candidate) => candidate.id === projectId);
  const activeKills = projectData.flags.filter((flag) => {
    const state = projectData.stateFor(flag);
    return !state.enabled;
  }).length;

  if (!organization || !project) return <div className="error-banner">Project not found.</div>;

  return (
    <div className="project-subpage flags-page">
      <div className="subpage-heading-row flags-heading-row">
        <div><span className="eyebrow">Control room</span><h2>Feature flags</h2><p>Make a measured decision, then keep the signal visible to everyone.</p></div>
        <button type="button" className="btn-primary" onClick={() => setPanelOpen(true)}><span aria-hidden="true">+</span> Create Flag</button>
      </div>

      <div className="flag-stats-row">
        <div><span>Active environment</span><strong>{projectData.activeEnv.toUpperCase()}</strong></div>
        <div><span>Live flags</span><strong>{projectData.flags.length - activeKills}</strong></div>
        <div><span>Emergency kills</span><strong className={activeKills ? 'danger-text' : 'success-text'}>{activeKills}</strong></div>
        <Link className="flag-stats-link" to={`/app/orgs/${orgId}/projects/${projectId}/environments`}>Manage environments <span aria-hidden="true">→</span></Link>
      </div>

      {projectData.error && <div className="error-banner">{projectData.error}</div>}
      {projectData.loading && projectData.flags.length === 0 ? (
        <div className="page-loading">Loading feature flags…</div>
      ) : projectData.flags.length === 0 ? (
        <div className="empty-state flags-empty-state"><div className="empty-illustration flag-empty" aria-hidden="true"><span>✦</span></div><h2>Your first flag is waiting.</h2><p>Create a flag to start shaping a safe, observable rollout for this project.</p><button type="button" className="btn-primary" onClick={() => setPanelOpen(true)}>Create your first flag <span aria-hidden="true">→</span></button></div>
      ) : (
        <div className="flag-list">{projectData.flags.map((flag) => <FlagCard key={flag.id} flag={flag} projectData={projectData} />)}</div>
      )}

      <FlagCreatePanel open={panelOpen} onClose={() => setPanelOpen(false)} projectData={projectData} />
    </div>
  );
}
