import { useState } from 'react';
import { Link, useNavigate, useParams } from 'react-router-dom';
import type { FormEvent } from 'react';

import { getErrorMessage } from '../api';
import { useWorkspace } from '../workspace/WorkspaceContext';

const STANDARD_ENVIRONMENTS = ['dev', 'staging', 'prod'];

export function CreateProjectPage() {
  const { orgId } = useParams();
  const { getOrganization, createProject } = useWorkspace();
  const navigate = useNavigate();
  const organization = getOrganization(orgId);
  const [name, setName] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!orgId || !organization) {
    return <div className="error-banner">Organization not found or no longer accessible.</div>;
  }

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const project = await createProject(orgId, name.trim());
      navigate(`/app/orgs/${orgId}/projects/${project.id}`, { replace: true });
    } catch (requestError) {
      setError(getErrorMessage(requestError, 'Unable to create project'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="form-page">
      <div className="form-page-back"><Link to={`/app/orgs/${orgId}`}>← Back to {organization.name}</Link></div>
      <div className="form-page-layout">
        <div className="form-page-intro">
          <span className="eyebrow">Step 02 · Project</span>
          <h1>Give your next<br /><em>release a room.</em></h1>
          <p>Projects keep flags and environments isolated, so every service can move at its own pace.</p>
          <div className="environment-preview">
            <span className="preview-label">Automatically provisioned</span>
            <div>{STANDARD_ENVIRONMENTS.map((environment) => <span className="env-badge standard" key={environment}>{environment}</span>)}</div>
            <p>Each project starts with a safe, familiar release path.</p>
          </div>
        </div>
        <section className="form-card">
          <div className="form-card-heading">
            <span className="eyebrow">Create project</span>
            <h2>What are you building?</h2>
            <p>You can add custom environments after setup.</p>
          </div>
          <form className="stacked-form" onSubmit={submit}>
            <div className="form-group">
              <label className="form-label" htmlFor="project-name">Project name</label>
              <input
                id="project-name"
                className="form-input form-input-large"
                required
                maxLength={255}
                placeholder="e.g. Web App"
                value={name}
                onChange={(event) => setName(event.target.value)}
                autoFocus
              />
              <span className="form-hint">Use the name your team already uses for this service.</span>
            </div>
            <div className="form-callout"><span aria-hidden="true">✦</span><span>New projects are private to <strong>{organization.name}</strong>.</span></div>
            {error && <div className="form-error" role="alert">{error}</div>}
            <div className="form-actions">
              <Link className="btn-secondary" to={`/app/orgs/${orgId}`}>Cancel</Link>
              <button type="submit" className="btn-primary" disabled={busy || !name.trim()}>
                {busy ? 'Creating…' : 'Create project'} <span aria-hidden="true">→</span>
              </button>
            </div>
          </form>
        </section>
      </div>
    </div>
  );
}
