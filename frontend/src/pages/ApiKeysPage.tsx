import { useCallback, useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';

import { createApiKey, fetchApiKeys, revokeApiKey } from '../api';
import type { ApiKey } from '../api';

export function ApiKeysPage() {
  const { projectId } = useParams();
  const [keys, setKeys] = useState<ApiKey[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [creating, setCreating] = useState(false);
  const [showCreateModal, setShowCreateModal] = useState(false);
  const [showKeyReveal, setShowKeyReveal] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [newKeyEnv, setNewKeyEnv] = useState('prod');
  const [newlyCreatedKey, setNewlyCreatedKey] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const _loadKeys = useCallback(async () => {
    try {
      const data = await fetchApiKeys(projectId || '');
      setKeys(data.keys);
      setError(null);
    } catch (err) {
      setError('Failed to load API keys');
      console.error(err);
    } finally {
      setLoading(false);
    }
  }, [projectId]);

  // Load keys when component mounts or projectId changes
  useEffect(() => {
    let active = true;
    if (projectId) {
      fetchApiKeys(projectId)
        .then((data) => {
          if (active) {
            setKeys(data.keys);
            setError(null);
            setLoading(false);
          }
        })
        .catch((err) => {
          if (active) {
            setError('Failed to load API keys');
            console.error(err);
            setLoading(false);
          }
        });
    }
    return () => {
      active = false;
    };
  }, [projectId]);

  const handleCreateKey = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!newKeyName.trim() || !newKeyEnv || !projectId) return;

    setCreating(true);
    try {
      const key = await createApiKey(projectId, {
        name: newKeyName.trim(),
        env: newKeyEnv,
      });
      setNewlyCreatedKey(key.prefix);
      setShowKeyReveal(true);
      setShowCreateModal(false);
      setNewKeyName('');
      setNewKeyEnv('prod');
      await _loadKeys();
    } catch (err) {
      setError('Failed to create API key');
      console.error(err);
    } finally {
      setCreating(false);
    }
  };

  const handleRevokeKey = async (keyId: string) => {
    if (!projectId) return;
    if (!window.confirm('Are you sure you want to revoke this API key? It cannot be undone.')) {
      return;
    }

    try {
      await revokeApiKey(projectId, keyId);
      await _loadKeys();
    } catch (err) {
      setError('Failed to revoke API key');
      console.error(err);
    }
  };

  const maskApiKey = (prefix: string) => {
    // Show format like: cp_prod_abc...xyz (first 12 chars + ... + last 4 chars)
    if (prefix.length <= 16) return prefix;
    const start = prefix.substring(0, 12);
    const end = prefix.substring(prefix.length - 4);
    return `${start}...${end}`;
  };

  const copyToClipboard = async (text: string) => {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    } catch {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.style.position = 'fixed';
      textarea.style.opacity = '0';
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      try {
        document.execCommand('copy');
        setCopied(true);
        setTimeout(() => setCopied(false), 2000);
      } finally {
        document.body.removeChild(textarea);
      }
    }
  };

  if (!projectId) {
    return <div className="error-banner">Project not found.</div>;
  }

  return (
    <div className="project-subpage keys-page">
      <div className="subpage-heading-row keys-heading-row">
        <div><span className="eyebrow">Control room</span><h2>API Keys</h2><p>Manage SDK tokens for programmatic flag evaluation.</p></div>
        <button type="button" className="btn-primary" onClick={() => setShowCreateModal(true)}><span aria-hidden="true">+</span> Create Key</button>
      </div>

      {error && <div className="error-banner">{error}</div>}

      {loading ? (
        <div className="page-loading">Loading API keys…</div>
      ) : keys === null || keys.length === 0 ? (
        <div className="empty-state flags-empty-state">
          <div className="empty-illustration flag-empty" aria-hidden="true"><span>✦</span></div>
          <h2>No API keys yet.</h2>
          <p>Create an API key to enable SDK authentication for your project.</p>
          <button type="button" className="btn-primary" onClick={() => setShowCreateModal(true)}>Create your first API key <span aria-hidden="true">→</span></button>
        </div>
      ) : (
        <div className="key-list">
          {keys.map((key: ApiKey) => (
            <div key={key.id} className={`key-card ${key.revoked ? 'revoked' : 'active'}`}>
              <div className="key-header">
                <div>
                  <h3>{key.name}</h3>
                  <div className="key-meta">
                    <span className="key-prefix">{maskApiKey(key.prefix)}</span>
                    <span className="key-separator">•</span>
                    <span className="key-env">{key.env}</span>
                    <span className="key-separator">•</span>
                    <span className="key-created">Created {new Date(key.created_at).toLocaleDateString()}</span>
                  </div>
                </div>
                <div className="key-actions">
                  {key.revoked ? (
                    <span className="key-status revoked-status">Revoked</span>
                  ) : (
                    <div className="key-actions-group">
                      <button
                        type="button"
                        className="btn-secondary btn-revoke"
                        onClick={() => handleRevokeKey(key.id)}
                      >
                        Revoke
                      </button>
                    </div>
                  )}
                </div>
              </div>
            </div>
          ))}
        </div>
      )}

      {/* Create API Key Modal */}
      {showCreateModal && (
        <div className="modal-overlay" onClick={() => setShowCreateModal(false)}>
          <div className="modal-card" onClick={(e) => e.stopPropagation()}>
            <div className="modal-header">
              <h2>Create API Key</h2>
              <button type="button" className="btn-close" onClick={() => setShowCreateModal(false)}>
                <span aria-hidden="true">×</span>
              </button>
            </div>
            <form onSubmit={handleCreateKey}>
              <div className="form-group">
                <label htmlFor="keyName" className="form-label">Key Name</label>
                <input
                  id="keyName"
                  type="text"
                  className="form-input"
                  value={newKeyName}
                  onChange={(e) => setNewKeyName(e.target.value)}
                  placeholder="e.g., Production SDK Key"
                  required
                  disabled={creating}
                />
                <p className="form-hint">A descriptive name for this API key.</p>
              </div>
              <div className="form-group">
                <label htmlFor="keyEnv" className="form-label">Environment</label>
                <select
                  id="keyEnv"
                  className="form-input"
                  value={newKeyEnv}
                  onChange={(e) => setNewKeyEnv(e.target.value)}
                  disabled={creating}
                >
                  <option value="dev">dev</option>
                  <option value="staging">staging</option>
                  <option value="prod">prod</option>
                </select>
                <p className="form-hint">The environment this key will provide access to.</p>
              </div>
              <div className="modal-actions">
                <button
                  type="button"
                  className="btn-secondary"
                  onClick={() => setShowCreateModal(false)}
                  disabled={creating}
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="btn-primary"
                  disabled={creating || !newKeyName.trim()}
                >
                  {creating ? 'Creating…' : 'Create API Key'}
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* Key Reveal Banner */}
      {showKeyReveal && newlyCreatedKey && (
        <div className="key-reveal-banner">
          <div className="key-reveal-content">
            <span className="reveal-icon">★</span>
            <p>
              <strong>Here is your API key:</strong> <code>{newlyCreatedKey}</code>
            </p>
            <p className="reveal-warning">This is the only time the key will be displayed. Store it securely.</p>
            <div className="reveal-actions">
              <button
                type="button"
                className="btn-secondary btn-copy"
                onClick={() => copyToClipboard(newlyCreatedKey)}
              >
                {copied ? 'Copied!' : 'Copy Key'}
              </button>
              <button
                type="button"
                className="btn-primary btn-done"
                onClick={() => {
                  setShowKeyReveal(false);
                  setNewlyCreatedKey(null);
                }}
              >
                I've saved my key
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
