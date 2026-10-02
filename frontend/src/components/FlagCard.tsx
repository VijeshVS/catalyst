import type { Flag } from '../api';
import { EvalPlayground } from './EvalPlayground';
import { KillSwitchButton } from './KillSwitchButton';
import { RolloutSlider } from './RolloutSlider';
import { RuleBuilder } from './RuleBuilder';
import type { ProjectData } from '../workspace/useProject';

interface FlagCardProps {
  flag: Flag;
  projectData: ProjectData;
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
