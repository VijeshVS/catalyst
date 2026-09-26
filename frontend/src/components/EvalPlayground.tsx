import { useState } from 'react';

import { ATTRIBUTE_CATALOG, attributeGroups } from '../lib/attributeCatalog';
import { formatAttributeInput, parseAttributeInput } from '../lib/targeting';
import type { ProjectData } from '../workspace/useProject';

interface EvalPlaygroundProps {
  flagKey: string;
  projectData: ProjectData;
}

const REASON_LABELS: Record<string, string> = {
  RULE_MATCH: 'Matched a targeting rule',
  KILL_SWITCH_ACTIVE: 'Kill switch active',
  PERCENTAGE_ROLLOUT: 'Matched the percentage rollout',
  DEFAULT_VALUE: 'No rule or rollout matched — flag default',
  FLAG_NOT_FOUND: 'Flag not found',
};

export function EvalPlayground({ flagKey, projectData }: EvalPlaygroundProps) {
  const saved = projectData.playground[flagKey];
  const [userId, setUserId] = useState(saved?.userId || 'user_123');
  const [attributeText, setAttributeText] = useState(() =>
    formatAttributeInput(saved?.attributes),
  );
  const [showPresets, setShowPresets] = useState(false);

  const updateText = (next: string) => {
    setAttributeText(next);
    // Publish the context so the rule builder's match preview tracks this input.
    projectData.setPlaygroundAttributes(flagKey, parseAttributeInput(next));
  };

  const addPreset = (key: string) => {
    const attributes = parseAttributeInput(attributeText);
    if (attributes[key] !== undefined) return;
    const spec = ATTRIBUTE_CATALOG.find((entry) => entry.key === key);
    const example = spec?.example;
    const suffix = example === undefined ? '' : `=${String(example)}`;
    updateText(attributeText ? `${attributeText}\n${key}${suffix}` : `${key}${suffix}`);
  };

  const submit = () => {
    void projectData.evaluate(flagKey, userId, parseAttributeInput(attributeText));
  };

  return (
    <div className="playground-box">
      <div className="playground-heading">
        <span className="eyebrow">Live evaluation</span>
        <span className="playground-hint">Test a sticky rollout without leaving the dashboard.</span>
      </div>
      <div className="playground-input-group">
        <label htmlFor={`playground-${flagKey}`}>Test user ID</label>
        <input
          id={`playground-${flagKey}`}
          type="text"
          className="playground-input"
          value={userId}
          onChange={(event) => setUserId(event.target.value)}
          placeholder="e.g. user_123 or alice@acme.com"
        />
      </div>
      <div className="playground-attributes">
        <div className="playground-attributes-head">
          <label htmlFor={`playground-attributes-${flagKey}`}>Attributes</label>
          <button
            type="button"
            className="text-button"
            aria-expanded={showPresets}
            onClick={() => setShowPresets((previous) => !previous)}
          >
            {showPresets ? 'Hide presets' : 'Add from presets'}
          </button>
        </div>
        {showPresets && (
          <div className="playground-presets">
            {attributeGroups().map((group) => (
              <div key={group.group} className="playground-preset-group">
                <span className="playground-preset-label">{group.group}</span>
                <div className="playground-preset-chips">
                  {group.specs.map((spec) => (
                    <button
                      key={spec.key}
                      type="button"
                      className="rule-token-suggestion"
                      title={spec.description}
                      onClick={() => addPreset(spec.key)}
                    >
                      <span aria-hidden="true">+</span> {spec.label}
                    </button>
                  ))}
                </div>
              </div>
            ))}
          </div>
        )}
        <textarea
          id={`playground-attributes-${flagKey}`}
          className="form-input playground-attributes-input"
          rows={3}
          value={attributeText}
          onChange={(event) => updateText(event.target.value)}
          placeholder={'email=alice@acme.com\nplan=pro\nversion=3'}
          spellCheck={false}
        />
        <span className="form-hint">
          Pick from the presets above, or write one <code>key=value</code> pair per line. Used by
          targeting rules.
        </span>
      </div>
      <div className="playground-actions">
        <button
          type="button"
          className="playground-btn"
          onClick={submit}
          disabled={saved?.evaluating}
        >
          {saved?.evaluating ? 'Evaluating…' : 'Evaluate'}
        </button>
      </div>
      {saved?.result && (
        <div className="evaluation-result" aria-live="polite">
          <span className={`eval-badge ${saved.result.value ? 'true' : 'false'}`}>
            Served: {saved.result.value ? 'True' : 'False'}
          </span>
          <span className="evaluation-reason">
            {REASON_LABELS[saved.result.reason] ?? saved.result.reason}
          </span>
          {saved.result.rule_id && (
            <span className="evaluation-rule">rule {saved.result.rule_id.slice(0, 8)}</span>
          )}
        </div>
      )}
    </div>
  );
}
