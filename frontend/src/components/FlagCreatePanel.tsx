import { useState } from 'react';
import type { FormEvent } from 'react';

import { getErrorMessage } from '../api';
import type { ProjectData } from '../workspace/useProject';

interface FlagCreatePanelProps {
  open: boolean;
  onClose: () => void;
  projectData: ProjectData;
}

export function FlagCreatePanel({ open, onClose, projectData }: FlagCreatePanelProps) {
  const [key, setKey] = useState('');
  const [name, setName] = useState('');
  const [description, setDescription] = useState('');
  const [defaultValue, setDefaultValue] = useState(false);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const resetForm = () => {
    setKey('');
    setName('');
    setDescription('');
    setDefaultValue(false);
    setError(null);
  };

  const close = () => {
    resetForm();
    onClose();
  };

  if (!open) return null;

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setSaving(true);
    setError(null);
    try {
      await projectData.createFlag({
        key: key.trim(),
        name: name.trim(),
        description: description.trim() || undefined,
        default_value: defaultValue,
      });
      resetForm();
      onClose();
    } catch (requestError) {
      setError(getErrorMessage(requestError, 'Unable to create feature flag'));
    } finally {
      setSaving(false);
    }
  };

  return (
    <div className="slide-over-backdrop" role="presentation" onMouseDown={close}>
      <aside
        className="slide-over-panel"
        role="dialog"
        aria-modal="true"
        aria-labelledby="create-flag-title"
        onMouseDown={(event) => event.stopPropagation()}
      >
        <div className="slide-over-header">
          <div>
            <span className="eyebrow">Project configuration</span>
            <h2 id="create-flag-title">Create feature flag</h2>
          </div>
          <button type="button" className="icon-button" onClick={close} aria-label="Close panel">
            ×
          </button>
        </div>
        <p className="slide-over-intro">
          Add a flag to <strong>{projectData.activeEnv}</strong>. It will be seeded into every project
          environment and invalidate the SDK bootstrap cache.
        </p>
        <form onSubmit={submit} className="stacked-form">
          <div className="form-group">
            <label className="form-label" htmlFor="flag-key">Flag key</label>
            <input
              id="flag-key"
              className="form-input"
              required
              pattern="[a-z0-9._-]+"
              placeholder="new-checkout-v2"
              value={key}
              onChange={(event) => setKey(event.target.value)}
            />
            <span className="form-hint">Lowercase letters, numbers, dots, hyphens, and underscores.</span>
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="flag-name">Display name</label>
            <input
              id="flag-name"
              className="form-input"
              required
              placeholder="New Checkout Flow"
              value={name}
              onChange={(event) => setName(event.target.value)}
            />
          </div>
          <div className="form-group">
            <label className="form-label" htmlFor="flag-description">Description</label>
            <textarea
              id="flag-description"
              className="form-input"
              rows={4}
              placeholder="What does this flag control?"
              value={description}
              onChange={(event) => setDescription(event.target.value)}
            />
          </div>
          <label className="checkbox-field">
            <input
              type="checkbox"
              checked={defaultValue}
              onChange={(event) => setDefaultValue(event.target.checked)}
            />
            <span>
              <strong>Use true as the safe default</strong>
              <small>Served when the rollout is 0% or the kill switch is active.</small>
            </span>
          </label>
          {error && <div className="form-error">{error}</div>}
          <div className="form-actions">
            <button type="button" className="btn-secondary" onClick={close}>Cancel</button>
            <button type="submit" className="btn-primary" disabled={saving}>
              {saving ? 'Creating…' : 'Create flag'}
            </button>
          </div>
        </form>
      </aside>
    </div>
  );
}
