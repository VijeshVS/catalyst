import { Link } from 'react-router-dom';

import { HealthIndicator } from './HealthIndicator';
import { UserMenu } from './UserMenu';

export function GlobalHeader() {
  return (
    <header className="global-header">
      <Link className="global-brand" to="/app" aria-label="Catalyst workspace">
        <span className="brand-logo small">C</span>
        <span>
          <strong>Catalyst</strong>
          <small>Feature control plane</small>
        </span>
      </Link>
      <div className="global-header-actions">
        <HealthIndicator />
        <UserMenu />
      </div>
    </header>
  );
}
