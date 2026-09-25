import { useEffect, useState } from 'react';

import { fetchHealth } from '../api';
import type { HealthStatus } from '../api';

export function HealthIndicator() {
  const [health, setHealth] = useState<HealthStatus | null>(null);

  useEffect(() => {
    let active = true;
    const load = async () => {
      try {
        const next = await fetchHealth();
        if (active) setHealth(next);
      } catch {
        if (active) setHealth(null);
      }
    };
    void load();
    const interval = window.setInterval(() => void load(), 5000);
    return () => {
      active = false;
      window.clearInterval(interval);
    };
  }, []);

  const healthy = health?.status === 'ok';
  return (
    <div className={`health-badge ${healthy ? 'healthy' : 'connecting'}`} title="API, PostgreSQL, and Redis status">
      <span className="health-dot" aria-hidden="true" />
      <span>{healthy ? 'Systems nominal' : health ? 'Systems degraded' : 'Connecting…'}</span>
    </div>
  );
}
