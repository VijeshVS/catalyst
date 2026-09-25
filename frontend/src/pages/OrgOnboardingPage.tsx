import { useMemo, useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import type { FormEvent } from 'react';

import { getErrorMessage } from '../api';
import { useWorkspace } from '../workspace/WorkspaceContext';

function slugify(value: string): string {
  return value
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, '-')
    .replace(/^-+|-+$/g, '')
    .slice(0, 48);
}

export function OrgOnboardingPage() {
  const { createOrganization } = useWorkspace();
  const navigate = useNavigate();
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const preview = useMemo(() => slugify(name) || 'your-organization', [name]);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      const organization = await createOrganization(name.trim(), description.trim() || undefined);
      navigate(`/app/orgs/${organization.id}`, { replace: true });
    } catch (requestError) {
      setError(getErrorMessage(requestError, 'Unable to create organization'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="form-page">
      <div className="form-page-back"><Link to="/app">← Back to workspace</Link></div>
      <div className="form-page-layout">
        <div className="form-page-intro">
          <span className="eyebrow">Step 01 · Organization</span>
          <h1>Give your work<br /><em>a home.</em></h1>
          <p>Organizations keep projects, environments, and flags together while giving every team a clear boundary.</p>
          <div className="form-preview-card">
            <span className="preview-label">Workspace slug preview</span>
            <strong>{preview}</strong>
            <span className="preview-url">catalyst.app/{preview}</span>
          </div>
        </div>
        <section className="form-card">
          <div className="form-card-heading">
            <span className="eyebrow">Create organization</span>
            <h2>Start with the essentials.</h2>
            <p>You can add projects and custom environments next.</p>
          </div>
          <form className="stacked-form" onSubmit={submit}>
            <div className="form-group">
              <label className="form-label" htmlFor="org-name">Organization name</label>
              <input
                id="org-name"
                className="form-input form-input-large"
                required
                maxLength={255}
                placeholder="e.g. Acme Labs"
                value={name}
                onChange={(event) => setName(event.target.value)}
                autoFocus
              />
              <span className="form-hint">This becomes the name your team sees in the workspace.</span>
            </div>
            <div className="form-group">
              <label className="form-label" htmlFor="org-description">Description <span className="optional-label">Optional</span></label>
              <textarea
                id="org-description"
                className="form-input"
                rows={5}
                maxLength={500}
                placeholder="What are you shipping here?"
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
              <span className="form-hint character-count">{description.length}/500</span>
            </div>
            {error && <div className="form-error" role="alert">{error}</div>}
            <div className="form-actions">
              <Link className="btn-secondary" to="/app">Cancel</Link>
              <button type="submit" className="btn-primary" disabled={busy || !name.trim()}>
                {busy ? 'Creating…' : 'Create organization'} <span aria-hidden="true">→</span>
              </button>
            </div>
          </form>
        </section>
      </div>
    </div>
  );
}
