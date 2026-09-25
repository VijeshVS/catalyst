import { useEffect } from 'react';
import { Link, useNavigate } from 'react-router-dom';

import { useWorkspace } from '../workspace/WorkspaceContext';

export function AppEntryPage() {
  const { organizations, selectedOrgId, loading, error } = useWorkspace();
  const navigate = useNavigate();

  useEffect(() => {
    if (loading || organizations.length === 0) return;
    const target = selectedOrgId ?? organizations[0].id;
    navigate(`/app/orgs/${target}`, { replace: true });
  }, [loading, navigate, organizations, selectedOrgId]);

  if (loading) {
    return (
      <div className="page-loading" role="status">
        <span className="loader-mark">C</span>
        <p>Opening your workspace…</p>
      </div>
    );
  }

  if (error && organizations.length === 0) {
    return <div className="error-banner">{error}</div>;
  }

  return (
    <div className="onboarding-page">
      <div className="onboarding-illustration" aria-hidden="true">
        <span className="illustration-ring ring-a" />
        <span className="illustration-ring ring-b" />
        <span className="illustration-core">C</span>
        <span className="illustration-spark spark-a">✦</span>
        <span className="illustration-spark spark-b">+</span>
      </div>
      <span className="eyebrow">Your control plane starts here</span>
      <h1 aria-label="Create your first Organization">Create your first<br /><em>Organization.</em></h1>
      <p>Bring your projects, environments, and feature flags together in one calm workspace.</p>
      <Link className="btn-primary btn-large" to="/app/orgs/new">Create an organization <span aria-hidden="true">→</span></Link>
      <div className="onboarding-note"><span>01</span> You can create more organizations anytime.</div>
    </div>
  );
}
