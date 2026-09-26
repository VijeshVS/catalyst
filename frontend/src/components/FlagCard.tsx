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
            <span className="flag-default-label">
              Default: {flag.default_value ? 'true' : 'false'}
            </span>
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
