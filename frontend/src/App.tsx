import React, { useState, useEffect } from 'react';
import './App.css';
import type { Environment, Flag, HealthStatus, EvaluateResult, Organization } from './api';
import {
  fetchFlags,
  fetchHealth,
  createFlag,
  updateFlagEnvState,
  evaluateFlag,
  fetchOrganizations,
  createOrganization,
  createProject,
  fetchProjectEnvironments,
  createEnvironment,
} from './api';

const STANDARD_ENVIRONMENTS = ['dev', 'staging', 'prod'];

type View = 'flags' | 'environments';

export function App() {
  // Workspace navigation (organization / project / environment)
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [workspaceLoaded, setWorkspaceLoaded] = useState(false);
  const [selectedOrgId, setSelectedOrgId] = useState<string | null>(null);
  const [selectedProjectId, setSelectedProjectId] = useState<string | null>(null);
  const [environments, setEnvironments] = useState<Environment[]>([]);
  const [env, setEnv] = useState('dev');
  const [view, setView] = useState<View>('flags');

  const [flags, setFlags] = useState<Flag[]>([]);
  const [health, setHealth] = useState<HealthStatus | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Create Flag modal
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [newKey, setNewKey] = useState('');
  const [newName, setNewName] = useState('');
  const [newDesc, setNewDesc] = useState('');
  const [newDefault, setNewDefault] = useState(false);

  // Workspace modals (New Organization / New Project)
  const [isOrgModalOpen, setIsOrgModalOpen] = useState(false);
  const [orgNameInput, setOrgNameInput] = useState('');
  const [isProjectModalOpen, setIsProjectModalOpen] = useState(false);
  const [projectNameInput, setProjectNameInput] = useState('');
  const [modalError, setModalError] = useState<string | null>(null);
  const [modalBusy, setModalBusy] = useState(false);

  // Environment management
  const [newEnvName, setNewEnvName] = useState('');
  const [envError, setEnvError] = useState<string | null>(null);
  const [envBusy, setEnvBusy] = useState(false);

  // Playground state per flag: { [flagKey]: { userId: string, result?: EvaluateResult, evaluating?: boolean } }
  const [playground, setPlayground] = useState<Record<string, { userId: string; result?: EvaluateResult; evaluating?: boolean }>>({});

  const selectedOrg = organizations.find((o) => o.id === selectedOrgId) || null;
  const projects = selectedOrg?.projects || [];
  const selectedProject = projects.find((p) => p.id === selectedProjectId) || null;
  const projectId = selectedProject?.id || null;

  // Keep the workspace selection consistent while data loads/changes.
  // Adjusting state during render (guarded so it always converges) avoids
  // extra effect passes; same-value updates are never queued.
  if (selectedOrgId) {
    const org = organizations.find((o) => o.id === selectedOrgId);
    const projectIsValid =
      !!org && !!selectedProjectId && org.projects.some((p) => p.id === selectedProjectId);
    if (!projectIsValid) {
      const nextProjectId = org?.projects[0]?.id ?? null;
      if (nextProjectId !== selectedProjectId) {
        setSelectedProjectId(nextProjectId);
      }
    }
  } else if (selectedProjectId) {
    setSelectedProjectId(null);
  }
  if (environments.length > 0 && !environments.some((e) => e.name === env)) {
    const nextEnv = environments[0].name;
    if (nextEnv !== env) {
      setEnv(nextEnv);
    }
  }

  // -------------------------------------------------------------------------
  // Data loading
  // -------------------------------------------------------------------------

  const loadOrganizations = async (): Promise<Organization[]> => {
    try {
      const data = await fetchOrganizations();
      setOrganizations(data);
      setSelectedOrgId((prev) => {
        if (prev && data.some((o) => o.id === prev)) return prev;
        return data[0]?.id ?? null;
      });
      setError(null);
      return data;
    } catch (err: any) {
      setError(err.message || 'Failed to load organizations');
      return [];
    }
  };

  const loadHealth = async () => {
    try {
      setHealth(await fetchHealth());
    } catch {
      setHealth(null);
    }
  };

  const loadProjectData = async (pid: string) => {
    try {
      const [flagsData, envsData] = await Promise.all([
        fetchFlags(pid),
        fetchProjectEnvironments(pid),
      ]);
      setFlags(flagsData);
      setEnvironments(envsData);
      setError(null);
    } catch (err: any) {
      setError(err.message || 'Failed to load project data');
    } finally {
      setLoading(false);
    }
  };

  // Initial workspace load + health polling
  useEffect(() => {
    (async () => {
      await loadOrganizations();
      setWorkspaceLoaded(true);
    })();
    loadHealth();
    const interval = setInterval(loadHealth, 5000);
    return () => clearInterval(interval);
  }, []);

  // Keep the selected project valid for the selected organization
  // (handled by the guarded render-phase adjustment above).

  // Load (and poll) flags/environments for the selected project
  useEffect(() => {
    if (!projectId) {
      setFlags([]);
      setEnvironments([]);
      setLoading(false);
      return;
    }
    setFlags([]);
    setLoading(true);
    loadProjectData(projectId);
    const interval = setInterval(() => loadProjectData(projectId), 5000);
    return () => clearInterval(interval);
  }, [projectId]);

  // Keep the environment selection valid for the project
  // (handled by the guarded render-phase adjustment above).

  // -------------------------------------------------------------------------
  // Flag actions
  // -------------------------------------------------------------------------

  const handleToggleKillSwitch = async (flag: Flag) => {
    if (!projectId) return;
    const currentState = flag.states.find((s) => s.env === env);
    const currentlyEnabled = currentState ? currentState.enabled : true;
    const newEnabled = !currentlyEnabled;

    try {
      await updateFlagEnvState(projectId, flag.key, env, { enabled: newEnabled });
      await loadProjectData(projectId);
    } catch (err: any) {
      alert('Error updating kill switch: ' + err.message);
    }
  };

  const handleRolloutChange = async (flag: Flag, percentage: number) => {
    if (!projectId) return;
    try {
      await updateFlagEnvState(projectId, flag.key, env, { percentage });
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
    if (!projectId) return;
    try {
      await createFlag(projectId, {
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
      await loadProjectData(projectId);
    } catch (err: any) {
      alert('Error creating flag: ' + err.message);
    }
  };

  const handlePlaygroundEvaluate = async (flagKey: string) => {
    if (!projectId) return;
    const state = playground[flagKey] || { userId: 'user_123' };
    const userId = state.userId || 'user_123';

    setPlayground((prev) => ({
      ...prev,
      [flagKey]: { ...state, evaluating: true },
    }));

    try {
      const res = await evaluateFlag({
        projectId,
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

  // -------------------------------------------------------------------------
  // Workspace actions
  // -------------------------------------------------------------------------

  const handleCreateOrg = async (e: React.FormEvent) => {
    e.preventDefault();
    setModalBusy(true);
    setModalError(null);
    try {
      const org = await createOrganization(orgNameInput.trim());
      setOrgNameInput('');
      setIsOrgModalOpen(false);
      setSelectedOrgId(org.id);
      setSelectedProjectId(null);
      await loadOrganizations();
    } catch (err: any) {
      setModalError(err.message);
    } finally {
      setModalBusy(false);
    }
  };

  const handleCreateProject = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!selectedOrgId) return;
    setModalBusy(true);
    setModalError(null);
    try {
      const project = await createProject(selectedOrgId, projectNameInput.trim());
      setProjectNameInput('');
      setIsProjectModalOpen(false);
      await loadOrganizations();
      setSelectedProjectId(project.id);
      setView('flags');
    } catch (err: any) {
      setModalError(err.message);
    } finally {
      setModalBusy(false);
    }
  };

  const handleCreateEnvironment = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!projectId) return;
    setEnvBusy(true);
    setEnvError(null);
    try {
      await createEnvironment(projectId, newEnvName.trim());
      setNewEnvName('');
      await loadProjectData(projectId);
    } catch (err: any) {
      setEnvError(err.message);
    } finally {
      setEnvBusy(false);
    }
  };

  const openOrgModal = () => {
    setModalError(null);
    setOrgNameInput('');
    setIsOrgModalOpen(true);
  };

  const openProjectModal = () => {
    setModalError(null);
    setProjectNameInput('');
    setIsProjectModalOpen(true);
  };

  const activeKillSwitches = flags.filter((f) => {
    const s = f.states.find((state) => state.env === env);
    return s && !s.enabled;
  }).length;

  const showOnboardingOrg = workspaceLoaded && !selectedOrg && !error;
  const showOnboardingProject = !!selectedOrg && !selectedProject;

  return (
    <div className="catalyst-container">
      {/* Error banner */}
      {error && (
        <div className="error-banner">
          ⚠️ {error}
        </div>
      )}

      {/* Header */}
      <header className="catalyst-header">
        <div className="brand-section">
          <div className="brand-logo">C</div>
          <div>
            <h1 className="brand-title">Catalyst</h1>
            <p className="brand-subtitle">Feature Flags & Rollout Management Platform</p>
          </div>
        </div>

        <div className="header-controls">
          {/* Organization / Project switcher */}
          <div className="workspace-switcher">
            <select
              className="workspace-select"
              aria-label="Organization"
              value={selectedOrgId ?? ''}
              onChange={(e) => setSelectedOrgId(e.target.value)}
              disabled={organizations.length === 0}
            >
              {organizations.length === 0 && <option value="">No organizations</option>}
              {organizations.map((o) => (
                <option key={o.id} value={o.id}>{o.name}</option>
              ))}
            </select>
            <span className="workspace-sep">/</span>
            <select
              className="workspace-select"
              aria-label="Project"
              value={selectedProjectId ?? ''}
              onChange={(e) => setSelectedProjectId(e.target.value)}
              disabled={projects.length === 0}
            >
              {projects.length === 0 && <option value="">No projects</option>}
              {projects.map((p) => (
                <option key={p.id} value={p.id}>{p.name}</option>
              ))}
            </select>
            <button className="btn-ghost" onClick={openOrgModal} title="Create a new organization">
              + Org
            </button>
            <button
              className="btn-ghost"
              onClick={openProjectModal}
              disabled={!selectedOrg}
              title="Create a new project"
            >
              + Project
            </button>
          </div>

          {/* Environment Switcher */}
          {environments.length > 0 && (
            <div className="env-selector">
              {environments.map((e) => (
                <button
                  key={e.id}
                  className={`env-btn ${env === e.name ? 'active' : ''}`}
                  onClick={() => setEnv(e.name)}
                >
                  {e.name.toUpperCase()}
                </button>
              ))}
            </div>
          )}

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

      {/* Onboarding: no organization yet */}
      {showOnboardingOrg ? (
        <div className="empty-state">
          <div className="empty-state-logo">C</div>
          <h2>Create your organization</h2>
          <p>
            Organizations group your projects, environments, and feature flags.
            Start by creating one.
          </p>
          <button className="btn-primary" style={{ margin: '0 auto' }} onClick={openOrgModal}>
            + Create Organization
          </button>
        </div>
      ) : showOnboardingProject ? (
        /* Organization without projects */
        <div className="empty-state">
          <h2>Create a project in “{selectedOrg?.name}”</h2>
          <p>
            Projects get their own isolated flags and the standard{' '}
            <strong>dev</strong>, <strong>staging</strong> and <strong>prod</strong>{' '}
            environments automatically.
          </p>
          <button className="btn-primary" style={{ margin: '0 auto' }} onClick={openProjectModal}>
            + New Project
          </button>
        </div>
      ) : selectedProject ? (
        <>
          {/* Stats Bar */}
          <div className="stats-grid">
            <div className="stat-card">
              <div className="stat-label">Total Flags</div>
              <div className="stat-value">{flags.length}</div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Active Environment</div>
              <div className="stat-value" style={{ color: 'var(--gold-bright)' }}>
                {env.toUpperCase()}
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Environments</div>
              <div className="stat-value" style={{ color: 'var(--gold-primary)' }}>
                {environments.length}
              </div>
            </div>
            <div className="stat-card">
              <div className="stat-label">Emergency Kills Active</div>
              <div
                className="stat-value"
                style={{ color: activeKillSwitches > 0 ? 'var(--danger-bright)' : 'var(--success)' }}
              >
                {activeKillSwitches}
              </div>
            </div>
          </div>

          {/* Action Bar with views */}
          <div className="action-bar">
            <div className="tabs">
              <button
                className={`tab-btn ${view === 'flags' ? 'active' : ''}`}
                onClick={() => setView('flags')}
              >
                Feature Flags
              </button>
              <button
                className={`tab-btn ${view === 'environments' ? 'active' : ''}`}
                onClick={() => setView('environments')}
              >
                Environments
              </button>
            </div>
            {view === 'flags' && (
              <button className="btn-primary" onClick={() => setIsModalOpen(true)}>
                + Create Flag
              </button>
            )}
          </div>

          {view === 'flags' ? (
            /* Flag List */
            loading && flags.length === 0 ? (
              <p className="loading-text">Loading feature flags...</p>
            ) : flags.length === 0 ? (
              <div className="flag-card empty-state">
                <p>No feature flags found in this project yet.</p>
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
                            <h3 className="flag-name">{flag.name}</h3>
                            <span className="flag-key-badge">{flag.key}</span>
                            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-muted)', letterSpacing: '0.5px', textTransform: 'uppercase' }}>
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
                          <span>{state.percentage}%</span>
                        </div>
                        <input
                          type="range"
                          min="0"
                          max="100"
                          value={state.percentage}
                          disabled={!state.enabled}
                          onChange={(e) => handleRolloutChange(flag, parseInt(e.target.value))}
                          className="rollout-slider"
                          style={{ '--value': `${state.percentage}%` } as React.CSSProperties}
                        />
                      </div>

                      {/* Live Evaluation Playground */}
                      <div className="playground-box">
                        <div className="playground-input-group">
                          <span>Test User ID:</span>
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
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', flexWrap: 'wrap' }}>
                            <span className={`eval-badge ${pgState.result.value ? 'true' : 'false'}`}>
                              {pgState.result.value ? 'SERVED: TRUE' : 'SERVED: FALSE'}
                            </span>
                            <span style={{ fontFamily: 'var(--font-mono)', fontSize: '10px', color: 'var(--text-muted)', letterSpacing: '0.3px' }}>
                              ({pgState.result.reason})
                            </span>
                          </div>
                        )}
                      </div>
                    </div>
                  );
                })}
              </div>
            )
          ) : (
            /* Environment management view */
            <div>
              <form className="env-create-row" onSubmit={handleCreateEnvironment}>
                <div className="form-group env-create-field">
                  <label className="form-label">New environment name</label>
                  <input
                    type="text"
                    required
                    pattern="^[a-z][a-z0-9_-]{0,63}$"
                    title="Lowercase letters, digits, hyphens or underscores"
                    placeholder="e.g. qa"
                    value={newEnvName}
                    onChange={(e) => setNewEnvName(e.target.value)}
                    className="form-input"
                  />
                </div>
                <button type="submit" className="btn-primary env-create-btn" disabled={envBusy}>
                  {envBusy ? 'Creating...' : '+ Create Environment'}
                </button>
              </form>

              {envError && <div className="form-error">⚠️ {envError}</div>}

              <div className="env-grid">
                {environments.map((environment) => {
                  const isStandard = STANDARD_ENVIRONMENTS.includes(environment.name);
                  return (
                    <div className="env-card" key={environment.id}>
                      <div className="env-card-head">
                        <span className="env-name">{environment.name.toUpperCase()}</span>
                        <span className={`env-badge ${isStandard ? 'standard' : 'custom'}`}>
                          {isStandard ? 'auto-created' : 'custom'}
                        </span>
                      </div>
                      <div className="env-meta">
                        Bootstrap cache version · <strong>v{environment.version}</strong>
                      </div>
                      <button
                        className="btn-ghost"
                        onClick={() => {
                          setEnv(environment.name);
                          setView('flags');
                        }}
                      >
                        View flags →
                      </button>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </>
      ) : null}

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

      {/* New Organization Modal */}
      {isOrgModalOpen && (
        <div className="modal-overlay" onClick={() => setIsOrgModalOpen(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h2 style={{ marginBottom: '18px' }}>New Organization</h2>
            <form onSubmit={handleCreateOrg}>
              <div className="form-group">
                <label className="form-label">Organization Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Acme Inc"
                  value={orgNameInput}
                  onChange={(e) => setOrgNameInput(e.target.value)}
                  className="form-input"
                />
              </div>
              <p className="modal-hint">
                An organization owns projects, environments, and their feature flags.
              </p>
              {modalError && <div className="form-error">⚠️ {modalError}</div>}
              <div className="modal-actions">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setIsOrgModalOpen(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={modalBusy}>
                  {modalBusy ? 'Creating...' : 'Create Organization'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* New Project Modal */}
      {isProjectModalOpen && (
        <div className="modal-overlay" onClick={() => setIsProjectModalOpen(false)}>
          <div className="modal-content" onClick={(e) => e.stopPropagation()}>
            <h2 style={{ marginBottom: '18px' }}>New Project</h2>
            <form onSubmit={handleCreateProject}>
              <div className="form-group">
                <label className="form-label">Project Name</label>
                <input
                  type="text"
                  required
                  placeholder="e.g. Web App"
                  value={projectNameInput}
                  onChange={(e) => setProjectNameInput(e.target.value)}
                  className="form-input"
                />
              </div>
              <div className="form-group">
                <label className="form-label">Environments (created automatically)</label>
                <div className="env-badges">
                  {STANDARD_ENVIRONMENTS.map((name) => (
                    <span key={name} className="env-badge standard">
                      {name}
                    </span>
                  ))}
                </div>
                <p className="modal-hint">
                  Every project starts with isolated <strong>dev</strong>,{' '}
                  <strong>staging</strong> and <strong>prod</strong> environments. More can
                  be added later.
                </p>
              </div>
              {modalError && <div className="form-error">⚠️ {modalError}</div>}
              <div className="modal-actions">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setIsProjectModalOpen(false)}
                >
                  Cancel
                </button>
                <button type="submit" className="btn-primary" disabled={modalBusy}>
                  {modalBusy ? 'Creating...' : 'Create Project'}
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
