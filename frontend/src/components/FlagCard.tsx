import { useState } from 'react';

import type { Flag } from '../api';
import { copyText } from '../lib/clipboard';
import { EvalPlayground } from './EvalPlayground';
import { KillSwitchButton } from './KillSwitchButton';
import { RolloutSlider } from './RolloutSlider';
import { RuleBuilder } from './RuleBuilder';
import type { ProjectData } from '../workspace/useProject';

interface FlagCardProps {
  flag: Flag;
  projectData: ProjectData;
}

function CopyFlagKey({ flagKey }: { flagKey: string }) {
  const [copied, setCopied] = useState(false);

  const copy = async () => {
    // Do not claim a copy that did not happen: clipboard access can be denied.
    if (!(await copyText(flagKey))) return;
    setCopied(true);
    window.setTimeout(() => setCopied(false), 1600);
  };

  return (
    <button
      type="button"
      className="flag-key-copy"
      onClick={copy}
      title={copied ? 'Copied' : `Copy flag key ${flagKey}`}
      aria-label={`Copy flag key ${flagKey}`}
      data-copied={copied}
    >
      <svg viewBox="0 0 16 16" width="12" height="12" aria-hidden="true" focusable="false">
        <rect x="5.5" y="5.5" width="8" height="8" rx="1.5" fill="none" stroke="currentColor" strokeWidth="1.4" />
        <path d="M10.5 3.5h-7a1 1 0 0 0-1 1v7" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" />
      </svg>
    </button>
  );
}

export function FlagCard({ flag, projectData }: FlagCardProps) {
  const state = projectData.stateFor(flag);
  // The two switches bypass the slider entirely, so the slider is disabled
  // whenever either one is overriding it. Which one, and why, is spelled out
  // below rather than left for the reader to infer from a greyed-out control.
  const bypassedBy = !state.enabled
    ? 'The kill switch is on, so the rollout is not consulted.'
    : state.enable_all
      ? 'Enabled to all users, so the rollout is not consulted.'
      : null;

  return (
    <article className="flag-card">
      <div className="flag-card-header">
        <div className="flag-heading">
          <div className="flag-title-area">
            <h3 className="flag-name">{flag.name}</h3>
            <span className="flag-key-badge">{flag.key}</span>
            <CopyFlagKey flagKey={flag.key} />
          </div>
          {flag.description && <p className="flag-desc">{flag.description}</p>}
        </div>
        <div className="flag-switches">
          <KillSwitchButton
            enabled={state.enabled}
            onToggle={() => void projectData.toggleKillSwitch(flag)}
          />
          <button
            type="button"
            className={`enable-all-btn ${state.enable_all ? 'on' : ''}`}
            onClick={() => void projectData.toggleEnableAll(flag)}
            aria-pressed={state.enable_all}
            title={
              state.enabled
                ? 'Serve true to everyone, with no rules and no rollout'
                : 'The kill switch overrides this'
            }
          >
            <span className="enable-all-icon" aria-hidden="true">{state.enable_all ? '★' : '☆'}</span>
            <span>{state.enable_all ? 'Everyone' : 'Enable to all'}</span>
          </button>
        </div>
      </div>

      <p className="flag-precedence">
        {state.enabled
          ? state.enable_all
            ? 'Kill switch off → everyone gets the feature. Rules and the rollout are not consulted.'
            : 'Kill switch off → rules filter, then the rollout splits whoever is left.'
          : 'Kill switch on → nobody gets the feature. Nothing else is consulted.'}
      </p>

      <RolloutSlider
        percentage={state.percentage}
        disabled={!state.enabled || state.enable_all}
        hint={bypassedBy}
        onCommit={(percentage) => void projectData.updateRollout(flag, percentage)}
      />

      <RuleBuilder flag={flag} projectData={projectData} />

      <EvalPlayground flagKey={flag.key} projectData={projectData} />
    </article>
  );
}
