import { useState } from 'react';
import { useNavigate, useParams } from 'react-router-dom';
import type { FormEvent } from 'react';

import { getErrorMessage } from '../api';
import { EnvBadge } from '../components/EnvBadge';
import { useProjectData } from '../workspace/useProject';
import { useWorkspace } from '../workspace/WorkspaceContext';

export function EnvironmentsPage() {
  const { orgId, projectId } = useParams();
  const navigate = useNavigate();
  const { getOrganization } = useWorkspace();
  const projectData = useProjectData();
  const organization = getOrganization(orgId);
  const project = organization?.projects.find((candidate) => candidate.id === projectId);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await projectData.createEnvironment(name.trim());
      setName('');
    } catch (requestError) {
      setError(getErrorMessage(requestError, 'Unable to create environment'));
    } finally {
      setBusy(false);
    }
  };

  const viewFlags = (environment: string) => {
    projectData.setActiveEnv(environment);
    navigate(`/app/orgs/${orgId}/projects/${projectId}?env=${encodeURIComponent(environment)}`);
  };

  if (!organization || !project) return <div className="error-banner">Project not found.</div>;

  return (
    <div className="project-subpage environments-page">
      <div className="subpage-heading-row">
        <div><span className="eyebrow">Project configuration</span><h2>Environments</h2><p>Each lane is isolated, cache-aware, and ready for its own release rhythm.</p></div>
        <div className="environment-count-badge"><strong>{projectData.environments.length}</strong><span>total lanes</span></div>
      </div>

      <form className="environment-create-panel" onSubmit={submit}>
        <div className="environment-create-copy"><span className="plus-circle">+</span><div><h3>Add a custom environment</h3><p>Use a lowercase identifier such as <code>qa</code> or <code>perf-test</code>.</p></div></div>
        <div className="environment-create-controls">
          <input className="form-input" required pattern="[a-z][a-z0-9_-]{0,63}" maxLength={64} placeholder="e.g. qa" value={name} onChange={(event) => setName(event.target.value)} aria-label="New environment name" />
          <button className="btn-primary" type="submit" disabled={busy || !name.trim()}>{busy ? 'Adding…' : '+ New environment'}</button>
        </div>
        {error && <div className="form-error">{error}</div>}
      </form>

      <div className="environment-grid">
        {projectData.environments.map((environment) => {
          const isStandard = ['dev', 'staging', 'prod'].includes(environment.name);
          return (
            <article className={`environment-card ${projectData.activeEnv === environment.name ? 'selected' : ''}`} key={environment.id}>
              <div className="environment-card-top"><EnvBadge name={environment.name} /><span className={`env-type-label ${isStandard ? 'standard' : 'custom'}`}>{isStandard ? 'auto-created' : 'custom'}</span></div>
              <h3>{environment.name.toUpperCase()}</h3>
              <p>Bootstrap cache version <strong>v{environment.version}</strong></p>
              <div className="environment-card-footer"><span className="environment-ready"><i /> Ready for flags</span><button type="button" className="text-button" onClick={() => viewFlags(environment.name)}>View flags <span aria-hidden="true">→</span></button></div>
            </article>
          );
        })}
      </div>
    </div>
  );
}
