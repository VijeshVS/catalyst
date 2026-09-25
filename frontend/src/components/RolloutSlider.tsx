import type { CSSProperties } from 'react';

interface RolloutSliderProps {
  percentage: number;
  onChange: (percentage: number) => void;
  disabled?: boolean;
}

type SliderStyle = CSSProperties & { '--value'?: string };

export function RolloutSlider({ percentage, onChange, disabled = false }: RolloutSliderProps) {
  return (
    <div className="rollout-box">
      <div className="rollout-header">
        <span>Gradual Canary Rollout</span>
        <span>{percentage}%</span>
      </div>
      <input
        type="range"
        min="0"
        max="100"
        value={percentage}
        disabled={disabled}
        onChange={(event) => onChange(Number.parseInt(event.target.value, 10))}
        className="rollout-slider"
        style={{ '--value': `${percentage}%` } as SliderStyle}
        aria-label="Percentage rollout"
      />
      <div className="rollout-scale" aria-hidden="true">
        <span>0%</span>
        <span>50%</span>
        <span>100%</span>
      </div>
    </div>
  );
}
