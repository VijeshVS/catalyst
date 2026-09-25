import { useState } from 'react';

import type { ProjectData } from '../workspace/useProject';

interface EvalPlaygroundProps {
  flagKey: string;
  projectData: ProjectData;
}

export function EvalPlayground({ flagKey, projectData }: EvalPlaygroundProps) {
  const saved = projectData.playground[flagKey];
  const [userId, setUserId] = useState(saved?.userId || 'user_123');

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
        <button
          type="button"
          className="playground-btn"
          onClick={() => void projectData.evaluate(flagKey, userId)}
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
          <span className="evaluation-reason">{saved.result.reason}</span>
        </div>
      )}
    </div>
  );
}
