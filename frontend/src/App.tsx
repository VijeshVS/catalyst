import React, { useEffect, useState } from 'react';
import './App.css';
import type { EvaluateResult, Flag, HealthStatus } from './api';
import { createFlag, evaluateFlag, fetchFlags, fetchHealth, updateFlagEnvState } from './api';

const navItems = ['Overview', 'Feature Flags', 'Rollouts', 'Evaluation', 'Audit'];

export function App() {
  const [env, setEnv] = useState<'dev' | 'staging' | 'prod'>('dev');
  const [flags, setFlags] = useState<Flag[]>([]);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newKey, setNewKey] = useState('');
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [newDefault, setNewDefault] = useState(false);

  const [playground, setPlayground] = useState<Record<string, { userId: string; result?: EvaluateResult; evaluating?: boolean }>>({});

  const loadData = async () => {
    try {
      const [healthData, flagsData] = await Promise.all([fetchHealth().catch(() => null), fetchFlags().catch(() => [])]);
      if (healthData) setHealth(healthData);
      setFlags(flagsData);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to connect to Catalyst API');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadData();
    const interval = setInterval(loadData, 5000);
    return () => clearInterval(interval);
  }, []);

  const handleToggleKillSwitch = async (flag: Flag) => {
    const currentState = flag.states.find((s) => s.env === env);
    const currentlyEnabled = currentState ? currentState.enabled : true;
    const newEnabled = !currentlyEnabled;

    try {
      await updateFlagEnvState(flag.key, env, { enabled: newEnabled });
      await loadData();
    } catch (err: any) {
      alert(`Error updating kill switch: ${err.message}`);
    }
  };

  const handleRolloutChange = async (flag: Flag, percentage: number) => {
    try {
      await updateFlagEnvState(flag.key, env, { percentage });
      setFlags((prev) =>
        prev.map((f) => {
          if (f.id !== flag.id) return f;
          return {
            ...f,
            states: f.states.map((s) => (s.env === env ? { ...s, percentage } : s)),
          };
        })
      );
    } catch (err: any) {
      alert(`Error updating rollout %: ${err.message}`);
    }
  };

  const handleCreateFlag = async (e: React.FormEvent) => {
    e.preventDefault();
    try {
      await createFlag({
        key: newKey.trim(),
        name: newName.trim(),
        description: newDesc.trim() || undefined,
        default_value: newDefault,
      });
      setIsModalOpen(false);
      setNewKey('');
      setNewName('');
      setNewDesc('');
      setNewDefault(false);
      await loadData();
    } catch (err: any) {
      alert(`Error creating flag: ${err.message}`);
    }
  };

  const handlePlaygroundEvaluate = async (flagKey: string) => {
    const state = playground[flagKey] || { userId: 'user_123' };
    const userId = state.userId || 'user_123';

    setPlayground((prev) => ({
      ...prev,
      [flagKey]: { ...state, evaluating: true },
    }));

    try {
      const res = await evaluateFlag({
        flag_key: flagKey,
        env,
        user_id: userId,
      });
      setPlayground((prev) => ({
        ...prev,
        [flagKey]: { userId, result: res, evaluating: false },
      }));
    } catch {
      setPlayground((prev) => ({
        ...prev,
        [flagKey]: { ...state, evaluating: false },
      }));
    }
  };

  const activeKillSwitches = flags.filter((f) => {
    const s = f.states.find((state) => state.env === env);
    return s && !s.enabled;
  }).length;

  const healthIsOk = health?.status === 'ok';

  return (
    <div className="app-shell">
      <header className="top-header">
        <div className="top-header-left">
          <div className="brand-logo">C</div>
          <div>
            <h1 className="brand-title">Catalyst</h1>
            <p className="brand-subtitle">Feature Flags & Rollout Management Platform</p>
          </div>
        </div>

        <div className="top-header-right">
          <div className="env-selector">
            {(['dev', 'staging', 'prod'] as const).map((e) => (
              <button key={e} className={`env-btn ${env === e ? 'active' : ''}`} onClick={() => setEnv(e)}>
                {e.toUpperCase()}
              </button>
            ))}
          </div>
          <span className="header-account">@VijeshVS</span>
        </div>
      </header>

      <div className="shell-body">
        <aside className="left-rail">
          <nav className="rail-nav">
            {navItems.map((item, index) => (
              <button key={item} className={`rail-item ${index === 1 ? 'active' : ''}`} type="button">
                {item}
              </button>
            ))}
          </nav>
        </aside>

        <main className="dashboard-main">
          {error && <div className="error-banner">⚠️ {error}</div>}

          <section className="page-intro">
            <div>
              <h2 className="page-title">Feature Dashboard</h2>
              <p className="page-subtitle">Manage flags, rollout strategy, and runtime validation in one place.</p>
            </div>
            <button className="btn-primary" onClick={() => setIsModalOpen(true)}>
              + Create Flag
            </button>
          </section>

          <section className="dashboard-grid">
            <div className="stats-grid">
              <div className="dashboard-card stat-card">
                <div className="stat-label">Total Flags</div>
                <div className="stat-value">{flags.length}</div>
              </div>
              <div className="dashboard-card stat-card">
                <div className="stat-label">Active Environment</div>
                <div className="stat-value stat-value-env">{env.toUpperCase()}</div>
              </div>
              <div className="dashboard-card stat-card">
                <div className="stat-label">Emergency Kills Active</div>
                <div className={`stat-value ${activeKillSwitches > 0 ? 'stat-value-warning' : 'stat-value-good'}`}>
                  {activeKillSwitches}
                </div>
              </div>
            </div>

            <section className="dashboard-card flags-panel">
              <h3 className="section-heading">Feature Flags ({env.toUpperCase()})</h3>

              {loading && flags.length === 0 ? (
                <p className="loading-text">Loading feature flags...</p>
              ) : flags.length === 0 ? (
                <div className="empty-state">
                  <p>No feature flags found for this environment.</p>
                  <button className="btn-primary" onClick={() => setIsModalOpen(true)}>
                    Create your first flag
                  </button>
                </div>
              ) : (
                <div className="flag-list">
                  {flags.map((flag) => {
                    const state = flag.states.find((s) => s.env === env) || {
                      enabled: true,
                      percentage: 0,
                      version: 1,
                    };
                    const pgState = playground[flag.key] || { userId: 'user_123' };

                    return (
                      <div key={flag.id} className="flag-card">
                        <div className="flag-card-header">
                          <div>
                            <div className="flag-title-area">
                              <h4 className="flag-name">{flag.name}</h4>
                              <span className="flag-key-badge">{flag.key}</span>
                              <span className="flag-default">Default: {flag.default_value ? 'true' : 'false'}</span>
                            </div>
                            {flag.description && <p className="flag-desc">{flag.description}</p>}
                          </div>

                          <button
                            className={`kill-switch-btn ${state.enabled ? 'active' : 'killed'}`}
                            onClick={() => handleToggleKillSwitch(flag)}
                            title="Click to toggle Emergency Kill Switch"
                          >
                            {state.enabled ? '🛡️ Live (Active)' : '🚨 Emergency Killed'}
                          </button>
                        </div>

                        <div className="rollout-box">
                          <div className="rollout-header">
                            <span>Gradual Canary Rollout</span>
                            <span className="rollout-value">{state.percentage}%</span>
                          </div>
                          <input
                            type="range"
                            min="0"
                            max="100"
                            value={state.percentage}
                            disabled={!state.enabled}
                            onChange={(e) => handleRolloutChange(flag, Number.parseInt(e.target.value, 10))}
                            className="rollout-slider"
                          />
                        </div>

                        <div className="playground-box">
                          <div className="playground-input-group">
                            <span className="playground-label">Test User ID:</span>
                            <input
                              type="text"
                              className="playground-input"
                              value={pgState.userId}
                              onChange={(e) =>
                                setPlayground((prev) => ({
                                  ...prev,
                                  [flag.key]: { ...pgState, userId: e.target.value },
                                }))
                              }
                              placeholder="e.g. user_123 or alice@acme.com"
                            />
                            <button className="playground-btn" onClick={() => handlePlaygroundEvaluate(flag.key)} disabled={pgState.evaluating}>
                              {pgState.evaluating ? 'Evaluating...' : 'Evaluate'}
                            </button>
                          </div>

                          {pgState.result && (
                            <div>
                              <span className={`eval-badge ${pgState.result.value ? 'true' : 'false'}`}>
                                {pgState.result.value ? 'SERVED: TRUE' : 'SERVED: FALSE'}
                              </span>
                              <span className="eval-reason">({pgState.result.reason})</span>
                            </div>
                          )}
                        </div>
                      </div>
                    );
                  })}
                </div>
              )}
            </section>

            <aside className="dashboard-card side-panel">
              <h3 className="section-heading">System Health</h3>
              <p className="panel-subtext">Environment readiness and operational signals</p>
              <div className={`health-badge ${healthIsOk ? 'ok' : 'pending'}`}>
                <span className="health-dot" />
                <span>
                  {healthIsOk
                    ? `Healthy (${health?.database === 'ok' ? 'PG' : 'DB'} + ${health?.redis === 'ok' ? 'Redis' : 'Cache'})`
                    : 'Connecting to API...'}
                </span>
              </div>

              <div className="side-list">
                <div className="side-list-item">Row 1: KPI cards for usage and state.</div>
                <div className="side-list-item">Row 2: Main feature flag management panel.</div>
                <div className="side-list-item">Row 3: Rollout + evaluation tools inside each flag card.</div>
              </div>
            </aside>
          </section>
        </main>
      </div>

      {isModalOpen && (
        <div className="modal-overlay" onClick={() => setIsModalOpen(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h2 className="modal-title">Create Feature Flag</h2>
            <form onSubmit={handleCreateFlag}>
              <div className="form-group">
                <label className="form-label">Flag Key (unique)</label>
                <input
                  type="text"
                  required
                  pattern="^[a-z0-9-_.]+$"
                  placeholder="e.g. new-checkout-v2"
                  value={newKey}
                  onChange={(e) => setNewKey(e.target.value)}
                  className="form-input"
                />
              </div>
              <div className="form-group">
                <label className="form-label">Display Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. New Checkout Flow"
                  value={newName}
                  onChange={(e) => setNewName(e.target.value)}
                  className="form-input"
                />
              </div>
              <div className="form-group">
                <label className="form-label">Description</label>
                <textarea
                  placeholder="Optional details about this feature rollout"
                  value={newDesc}
                  onChange={(e) => setNewDesc(e.target.value)}
                  className="form-input"
                  rows={3}
                />
              </div>
              <div className="form-group form-checkbox-row">
                <input
                  type="checkbox"
                  id="defaultVal"
                  checked={newDefault}
                  onChange={(e) => setNewDefault(e.target.checked)}
                  className="form-checkbox"
                />
                <label htmlFor="defaultVal" className="form-checkbox-label">
                  Default Value (served when rollout is 0% or killed)
                </label>
              </div>

              <div className="modal-actions">
                <button type="button" className="btn-secondary" onClick={() => setIsModalOpen(false)}>
                  Cancel
                </button>
                <button type="submit" className="btn-primary">
                  Create Flag
                </button>
              </div>
            </form>
          </div>
        </div>
      )}
    </div>
  );
}

export default App;
