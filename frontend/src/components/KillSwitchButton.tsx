interface KillSwitchButtonProps {
  enabled: boolean;
  onToggle: () => void;
  disabled?: boolean;
}

export function KillSwitchButton({ enabled, onToggle, disabled = false }: KillSwitchButtonProps) {
  return (
    <button
      type="button"
      className={`kill-switch-btn ${enabled ? 'active' : 'killed'}`}
      onClick={onToggle}
      disabled={disabled}
      title="Toggle Emergency Kill Switch"
      aria-pressed={enabled}
    >
      <span className="kill-switch-icon" aria-hidden="true">{enabled ? '◈' : '!'}</span>
      <span>{enabled ? 'Live · Active' : 'Emergency Killed'}</span>
    </button>
  );
}
