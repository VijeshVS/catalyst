import { fireEvent, render, screen } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import { FlagCard } from '../components/FlagCard';
import type { Flag } from '../api';
import type { ProjectData } from '../workspace/useProject';

vi.mock('../components/EvalPlayground', () => ({
  EvalPlayground: () => <div data-testid="eval-playground" />,
}));

vi.mock('../components/RuleBuilder', () => ({
  RuleBuilder: () => <div data-testid="rule-builder" />,
}));

const flag: Flag = {
  id: 'flag-1',
  project_id: 'project-1',
  key: 'ai-assistant',
  name: 'AI Assistant',
  description: 'Controls the AI assistant widget',
  default_value: false,
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-02T00:00:00Z',
  states: [{ env: 'dev', enabled: true, percentage: 0, version: 1, updated_at: '2026-01-02T00:00:00Z' }],
  rules: [],
};

function renderCard(flagOverride: Partial<Flag> = {}) {
  const updateDefaultValue = vi.fn();
  const projectData = {
    flags: [{ ...flag, ...flagOverride }],
    environments: [{ id: 'env-1', project_id: 'project-1', name: 'dev', version: 1 }],
    activeEnv: 'dev',
    loading: false,
    error: null,
    playground: {},
    setActiveEnv: vi.fn(),
    refresh: vi.fn(),
    toggleKillSwitch: vi.fn(),
    updateRollout: vi.fn(),
    updateDefaultValue,
    createFlag: vi.fn(),
    createEnvironment: vi.fn(),
    createRule: vi.fn(),
    updateRule: vi.fn(),
    deleteRule: vi.fn(),
    moveRule: vi.fn(),
    evaluate: vi.fn(),
    setPlaygroundAttributes: vi.fn(),
    stateFor: vi.fn(() => ({ env: 'dev', enabled: true, percentage: 0, version: 1 })),
    rulesFor: vi.fn(() => []),
  } as unknown as ProjectData;

  const view = render(
    <FlagCard flag={{ ...flag, ...flagOverride }} projectData={projectData} />,
  );
  return { projectData, updateDefaultValue, view };
}

describe('FlagCard default value toggle', () => {
  it('displays the current default value', () => {
    renderCard();
    expect(screen.getByText('Default: false')).toBeInTheDocument();
  });

  it('flips the default value from false to true on click', () => {
    const { updateDefaultValue } = renderCard();

    fireEvent.click(screen.getByText('Default: false'));

    expect(updateDefaultValue).toHaveBeenCalledTimes(1);
    expect(updateDefaultValue).toHaveBeenCalledWith(flag, true);
  });

  it('flips the default value from true to false on click', () => {
    const { updateDefaultValue } = renderCard({ default_value: true });

    fireEvent.click(screen.getByText('Default: true'));

    expect(updateDefaultValue).toHaveBeenCalledWith(expect.objectContaining({ id: 'flag-1' }), false);
  });

  it('reflects the updated default value after a rerender', () => {
    const { projectData, view } = renderCard();

    view.rerender(<FlagCard flag={{ ...flag, default_value: true }} projectData={projectData} />);

    expect(screen.getByText('Default: true')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /default: true/i })).toHaveAttribute('aria-pressed', 'true');
  });
});
