import React, { useState, useEffect } from 'react';
import './App.css';
import type { Flag, HealthStatus, EvaluateResult } from './api';
import {
  fetchFlags,
  fetchHealth,
  createFlag,
  updateFlagEnvState,
  evaluateFlag,
} from './api';

export function App() {
  const [env, setEnv] = useState<'dev' | 'staging' | 'prod'>('dev');
  const [flags, setFlags] = useState<Flag[]>([]);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);


  // Modal
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newKey, setNewKey] = useState('');
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [newDefault, setNewDefault] = useState(false);

  // Playground state per flag: { [flagKey]: { userId: string, result?: EvaluateResult, evaluating?: boolean } }
  const [playground, setPlayground] = useState<Record<string, { userId: string; result?: EvaluateResult; evaluating?: boolean }>>({});

  const loadData = async () => {
    try {
      const [healthData, flagsData] = await Promise.all([
        fetchHealth().catch(() => null),
        fetchFlags().catch(() => []),
      ]);
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
      alert('Error updating kill switch: ' + err.message);
    }
  };

  const handleRolloutChange = async (flag: Flag, percentage: number) => {
    try {
      await updateFlagEnvState(flag.key, env, { percentage });
      // Optimistic update
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
      alert('Error updating rollout %: ' + err.message);
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
      alert('Error creating flag: ' + err.message);
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
    } catch (err: any) {
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

  return (
    <div className="catalyst-container">
      {/* Header */}
      {error && (
        <div style={{
          background: 'rgba(244, 63, 94, 0.15)',
          border: '1px solid rgba(244, 63, 94, 0.4)',
          color: '#fb7185',
          padding: '12px 16px',
          borderRadius: '8px',
          marginBottom: '20px',
          fontSize: '14px',
        }}>
          ⚠️ {error}
        </div>
      )}

      <header className="catalyst-header">
        <div className="brand-section">
          <div className="brand-logo">C</div>
          <div>
            <h1 className="brand-title">Catalyst</h1>
            <p className="brand-subtitle">Feature Flags & Rollout Management Platform</p>
          </div>
        </div>

        <div className="header-controls">
          {/* Environment Switcher */}
          <div className="env-selector">
            {(['dev', 'staging', 'prod'] as const).map((e) => (
              <button
                key={e}
                className={`env-btn ${env === e ? 'active' : ''}`}
                onClick={() => setEnv(e)}
              >
                {e.toUpperCase()}
              </button>
            ))}
          </div>

          {/* Health Status Pill */}
          <div className="health-badge">
            <span className="health-dot"></span>
            <span>
              {health?.status === 'ok'
                ? `System Healthy (${health.database === 'ok' ? 'PG' : 'DB'} + ${health.redis === 'ok' ? 'Redis' : 'Cache'})`
                : 'Connecting to API...'}
            </span>
          </div>
        </div>
      </header>

      {/* Stats Bar */}
      <div className="stats-grid">
        <div className="stat-card">
          <div className="stat-label">Total Flags</div>
          <div className="stat-value">{flags.length}</div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Active Environment</div>
          <div className="stat-value" style={{ color: 'var(--accent-cyan)' }}>
            {env.toUpperCase()}
          </div>
        </div>
        <div className="stat-card">
          <div className="stat-label">Emergency Kills Active</div>
          <div
            className="stat-value"
            style={{ color: activeKillSwitches > 0 ? 'var(--accent-rose)' : 'var(--accent-emerald)' }}
          >
            {activeKillSwitches}
          </div>
        </div>
      </div>

      {/* Action Bar */}
      <div className="action-bar">
        <h2 className="section-heading">Feature Flags ({env})</h2>
        <button className="btn-primary" onClick={() => setIsModalOpen(true)}>
          + Create Flag
        </button>
      </div>

      {/* Flag List */}
      {loading && flags.length === 0 ? (
        <p style={{ color: 'var(--text-secondary)' }}>Loading feature flags...</p>
      ) : flags.length === 0 ? (
        <div className="flag-card" style={{ textAlign: 'center', padding: '40px' }}>
          <p style={{ color: 'var(--text-secondary)', marginBottom: '16px' }}>
            No feature flags found for this environment.
          </p>
          <button className="btn-primary" style={{ margin: '0 auto' }} onClick={() => setIsModalOpen(true)}>
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
                      <h3 className="flag-name">{flag.name}</h3>
                      <span className="flag-key-badge">{flag.key}</span>
                      <span style={{ fontSize: '12px', color: 'var(--text-muted)' }}>
                        Default: {flag.default_value ? 'true' : 'false'}
                      </span>
                    </div>
                    {flag.description && <p className="flag-desc">{flag.description}</p>}
                  </div>

                  {/* Kill Switch Toggle */}
                  <button
                    className={`kill-switch-btn ${state.enabled ? 'active' : 'killed'}`}
                    onClick={() => handleToggleKillSwitch(flag)}
                    title="Click to toggle Emergency Kill Switch"
                  >
                    {state.enabled ? '🛡️ Live (Active)' : '🚨 EMERGENCY KILLED'}
                  </button>
                </div>

                {/* Rollout Slider */}
                <div className="rollout-box">
                  <div className="rollout-header">
                    <span>Gradual Canary Rollout</span>
                    <span style={{ color: 'var(--accent-cyan)' }}>{state.percentage}%</span>
                  </div>
                  <input
                    type="range"
                    min="0"
                    max="100"
                    value={state.percentage}
                    disabled={!state.enabled}
                    onChange={(e) => handleRolloutChange(flag, parseInt(e.target.value))}
                    className="rollout-slider"
                  />
                </div>

                {/* Live Evaluation Playground */}
                <div className="playground-box">
                  <div className="playground-input-group">
                    <span style={{ fontSize: '12px', color: 'var(--text-secondary)' }}>
                      Test User ID:
                    </span>
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
                    <button
                      className="playground-btn"
                      onClick={() => handlePlaygroundEvaluate(flag.key)}
                      disabled={pgState.evaluating}
                    >
                      {pgState.evaluating ? 'Evaluating...' : 'Evaluate'}
                    </button>
                  </div>

                  {pgState.result && (
                    <div>
                      <span className={`eval-badge ${pgState.result.value ? 'true' : 'false'}`}>
                        {pgState.result.value ? 'SERVED: TRUE' : 'SERVED: FALSE'}
                      </span>
                      <span style={{ fontSize: '11px', color: 'var(--text-muted)', marginLeft: '8px' }}>
                        ({pgState.result.reason})
                      </span>
                    </div>
                  )}
                </div>
              </div>
            );
          })}
        </div>
      )}

      {/* Create Flag Modal */}
      {isModalOpen && (
        <div className="modal-overlay" onClick={() => setIsModalOpen(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h2 style={{ marginBottom: '18px' }}>Create Feature Flag</h2>
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
              <div className="form-group" style={{ display: 'flex', alignItems: 'center', gap: '10px' }}>
                <input
                  type="checkbox"
                  id="defaultVal"
                  checked={newDefault}
                  onChange={(e) => setNewDefault(e.target.checked)}
                />
                <label htmlFor="defaultVal" style={{ fontSize: '13px', cursor: 'pointer' }}>
                  Default Value (served when rollout is 0% or killed)
                </label>
              </div>

              <div className="modal-actions">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setIsModalOpen(false)}
                >
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
