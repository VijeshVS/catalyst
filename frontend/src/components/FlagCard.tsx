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

  return (
    <article className="flag-card">
      <div className="flag-card-header">
        <div className="flag-heading">
          <div className="flag-title-area">
            <h3 className="flag-name">{flag.name}</h3>
            <span className="flag-key-badge">{flag.key}</span>
            <button
              type="button"
              className={`default-value-toggle${flag.default_value ? ' on' : ''}`}
              onClick={() => void projectData.updateDefaultValue(flag, !flag.default_value)}
              title="Safe default served when the rollout is 0% or the kill switch is active"
              aria-pressed={flag.default_value}
            >
              <span className="default-value-icon" aria-hidden="true">
                {flag.default_value ? '◈' : '○'}
              </span>
              <span>Default: {flag.default_value ? 'true' : 'false'}</span>
            </button>
          </div>
          {flag.description && <p className="flag-desc">{flag.description}</p>}
        </div>
        <KillSwitchButton
          enabled={state.enabled}
          onToggle={() => void projectData.toggleKillSwitch(flag)}
        />
      </div>

      <RolloutSlider
        percentage={state.percentage}
        disabled={!state.enabled}
        onCommit={(percentage) => void projectData.updateRollout(flag, percentage)}
      />

      <RuleBuilder flag={flag} projectData={projectData} />

      <EvalPlayground flagKey={flag.key} projectData={projectData} />
    </article>
  );
}
