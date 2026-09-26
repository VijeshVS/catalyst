import { useCallback, useEffect, useRef, useState } from 'react';
import type { CSSProperties } from 'react';

interface RolloutSliderProps {
  percentage: number;
  onCommit: (percentage: number) => void;
  disabled?: boolean;
  debounceMs?: number;
}

type SliderStyle = CSSProperties & { '--value'?: string };

/**
 * Canary rollout slider.
 *
 * A drag fires an `input` event per pixel, so committing on every change would
 * issue one PATCH per step and bump the environment version (and the audit log)
 * dozens of times for a single gesture. The thumb therefore moves on a local
 * draft and the mutation is debounced, then flushed immediately when the
 * interaction ends so a release never leaves an unsaved value behind.
 */
export function RolloutSlider({
  percentage,
  onCommit,
  disabled = false,
  debounceMs = 400,
}: RolloutSliderProps) {
  const [draft, setDraft] = useState(percentage);
  // True between a local edit and the commit that persists it, so the header can
  // say so instead of implying the server already has the new value.
  const [pending, setPending] = useState(false);
  // The `percentage` the draft was last derived from, so a server update can be
  // told apart from the user's own edit.
  const [syncedPercentage, setSyncedPercentage] = useState(percentage);
  const timer = useRef<number | null>(null);

  const clearTimer = useCallback(() => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current);
      timer.current = null;
    }
  }, []);

  const commit = useCallback(
    (value: number) => {
      clearTimer();
      setPending(false);
      if (value === percentage) return;
      onCommit(value);
    },
    [clearTimer, onCommit, percentage],
  );

  // The timer and the flush handlers call the latest `commit` through a ref, so
  // a new `onCommit` identity cannot restart a debounce that is already running.
  const commitRef = useRef(commit);
  useEffect(() => {
    commitRef.current = commit;
  }, [commit]);

  // Adopt server state during render, and only while the user is not mid-edit,
  // otherwise a background poll would yank the thumb back under their finger.
  if (percentage !== syncedPercentage) {
    setSyncedPercentage(percentage);
    if (!pending) setDraft(percentage);
  }

  const handleChange = useCallback(
    (value: number) => {
      setDraft(value);
      setPending(value !== percentage);
      clearTimer();
      timer.current = window.setTimeout(() => {
        timer.current = null;
        commitRef.current(value);
      }, debounceMs);
    },
    [clearTimer, debounceMs, percentage],
  );

  // Release, keyboard commit, and losing focus all mean "the user is done".
  const flush = useCallback(() => {
    if (timer.current === null) return;
    commitRef.current(draft);
  }, [draft]);

  useEffect(() => clearTimer, [clearTimer]);

  return (
    <div className="rollout-box">
      <div className="rollout-header">
        <span>Gradual Canary Rollout</span>
        <span>
          {draft}%
          {pending && <em className="rollout-pending">saving</em>}
        </span>
      </div>
      <input
        type="range"
        min="0"
        max="100"
        value={draft}
        disabled={disabled}
        onChange={(event) => handleChange(Number.parseInt(event.target.value, 10))}
        onPointerUp={flush}
        onKeyUp={flush}
        onBlur={flush}
        className="rollout-slider"
        style={{ '--value': `${draft}%` } as SliderStyle}
        aria-label="Percentage rollout"
        aria-valuetext={`${draft} percent${pending ? ', saving' : ''}`}
      />
      <div className="rollout-scale" aria-hidden="true">
        <span>0%</span>
        <span>50%</span>
        <span>100%</span>
      </div>
    </div>
  );
}
