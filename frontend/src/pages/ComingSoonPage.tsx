import { Link, useLocation } from 'react-router-dom';

export function ComingSoonPage() {
  const location = useLocation();
  const isAudit = location.pathname.endsWith('/audit');
  const isSettings = location.pathname.endsWith('/settings');
  const title = isAudit ? 'Audit log' : isSettings ? 'Project settings' : 'API keys';
  const phase = isAudit ? 'Phase 3' : isSettings ? 'Phase 3' : 'Phase 2';

  return (
    <div className="not-found-card coming-soon-card">
      <span className="eyebrow">{phase} · Coming soon</span>
      <div className="coming-soon-mark" aria-hidden="true">◌</div>
      <h1>{title}</h1>
      <p>This surface is intentionally held for a later roadmap phase. Your current project controls remain fully available.</p>
      <Link className="btn-secondary" to="..">← Back to project</Link>
    </div>
  );
}
