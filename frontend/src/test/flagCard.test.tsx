import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { FlagCard } from '../components/FlagCard';
import type { Flag, FlagState } from '../api';
import type { ProjectData } from '../workspace/useProject';

const flag: Flag = {
  id: 'flag-1',
  project_id: 'project-1',
  key: 'ai-assistant',
  name: 'AI Assistant',
  description: 'Controls the AI assistant widget',
  created_at: '2026-01-01T00:00:00Z',
  updated_at: '2026-01-02T00:00:00Z',
  states: [
    { env: 'dev', enabled: true, enable_all: false, percentage: 40, version: 1, updated_at: '2026-01-02T00:00:00Z' },
  ],
  rules: [],
};

function renderCard(stateOverrides: Partial<FlagState> = {}) {
  const state: FlagState = {
    ...flag.states[0],
    ...stateOverrides,
  };
  const toggleEnableAll = vi.fn();
  const toggleKillSwitch = vi.fn();
  const updateRollout = vi.fn();
  const projectData = {
    flags: [flag],
    environments: [{ id: 'env-1', project_id: 'project-1', name: 'dev', version: 1, created_at: '2026-01-01T00:00:00Z' }],
    activeEnv: 'dev',
    loading: false,
    error: null,
    playground: {},
    setActiveEnv: vi.fn(),
    refresh: vi.fn(),
    toggleKillSwitch,
    toggleEnableAll,
    updateRollout,
    createFlag: vi.fn(),
    createEnvironment: vi.fn(),
    createRule: vi.fn(),
    updateRule: vi.fn(),
    deleteRule: vi.fn(),
    moveRule: vi.fn(),
    evaluate: vi.fn(),
    setPlaygroundAttributes: vi.fn(),
    stateFor: vi.fn(() => state),
    rulesFor: vi.fn(() => []),
  } as unknown as ProjectData;

  const view = render(<FlagCard flag={flag} projectData={projectData} />);
  return { projectData, toggleEnableAll, toggleKillSwitch, updateRollout, view };
}

describe('FlagCard enable-to-all-users switch', () => {
  it('shows the switch as off by default', () => {
    renderCard();
    expect(screen.getByRole('button', { name: /enable to all/i })).toHaveAttribute(
      'aria-pressed',
      'false',
    );
  });

  it('flips the switch on click', () => {
    const { toggleEnableAll } = renderCard();
    fireEvent.click(screen.getByRole('button', { name: /enable to all/i }));
    expect(toggleEnableAll).toHaveBeenCalledTimes(1);
    expect(toggleEnableAll).toHaveBeenCalledWith(flag);
  });

  it('shows the switch as on once enable_all is set', () => {
    renderCard({ enable_all: true });
    expect(screen.getByRole('button', { name: /everyone/i })).toHaveAttribute(
      'aria-pressed',
      'true',
    );
  });
});

describe('FlagCard precedence is visible', () => {
  it('says the kill switch decides when it is on', () => {
    renderCard({ enabled: false });
    expect(screen.getByText(/Kill switch on/i)).toBeInTheDocument();
    expect(screen.getByText(/nothing else is consulted/i)).toBeInTheDocument();
  });

  it('says rules and rollout decide when both switches are off', () => {
    renderCard();
    expect(
      screen.getByText(/rules filter, then the rollout splits/i),
    ).toBeInTheDocument();
  });

  it('says everybody gets the feature when enable-all is on', () => {
    renderCard({ enable_all: true });
    expect(screen.getByText(/everyone gets the feature/i)).toBeInTheDocument();
    expect(
      screen.getByText(/Rules and the rollout are not consulted/i),
    ).toBeInTheDocument();
  });
});

describe('FlagCard rollout slider disabling', () => {
  it('is enabled when both switches are off', () => {
    renderCard();
    expect(screen.getByRole('slider')).not.toBeDisabled();
  });

  it('is disabled by the kill switch', () => {
    renderCard({ enabled: false });
    expect(screen.getByRole('slider')).toBeDisabled();
    expect(
      screen.getByText(/The kill switch is on, so the rollout is not consulted/i),
    ).toBeInTheDocument();
  });

  it('is disabled by enable-all, which also bypasses the rollout', () => {
    renderCard({ enable_all: true });
    expect(screen.getByRole('slider')).toBeDisabled();
    expect(
      screen.getByText(/Enabled to all users, so the rollout is not consulted/i),
    ).toBeInTheDocument();
  });
});

describe('FlagCard live evaluation is minimized', () => {
  it('starts collapsed, like the targeting rules section', () => {
    renderCard();

    const disclosure = screen.getByRole('button', { name: /live evaluation/i });
    expect(disclosure).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByLabelText(/test user id/i)).not.toBeInTheDocument();
  });

  it('opens the section when the disclosure is clicked', () => {
    renderCard();

    fireEvent.click(screen.getByRole('button', { name: /live evaluation/i }));

    expect(screen.getByRole('button', { name: /live evaluation/i })).toHaveAttribute(
      'aria-expanded',
      'true',
    );
    expect(screen.getByLabelText(/test user id/i)).toBeInTheDocument();
  });

  it('closes again on a second click', () => {
    renderCard();
    const disclosure = screen.getByRole('button', { name: /live evaluation/i });

    fireEvent.click(disclosure);
    fireEvent.click(disclosure);

    expect(disclosure).toHaveAttribute('aria-expanded', 'false');
    expect(screen.queryByLabelText(/test user id/i)).not.toBeInTheDocument();
  });

  it('says it has not been evaluated yet while collapsed', () => {
    renderCard();

    expect(screen.getByText(/not evaluated yet/i)).toBeInTheDocument();
  });

  it('keeps the decision readable while collapsed', () => {
    const { projectData, view } = renderCard();
    projectData.playground[flag.key] = {
      userId: 'user_123',
      attributes: {},
      evaluating: false,
      result: { flag_key: flag.key, value: false, reason: 'DEFAULT_VALUE', rule_id: null },
    };
    view.rerender(<FlagCard flag={flag} projectData={projectData} />);

    // Collapsed, but the answer to the thing you just evaluated is still there.
    expect(screen.queryByText(/not evaluated yet/i)).not.toBeInTheDocument();
    expect(screen.getByText(/no rule matched/i)).toBeInTheDocument();
    expect(screen.getByRole('button', { name: /live evaluation/i })).toHaveAttribute(
      'aria-expanded',
      'false',
    );
  });
});

describe('FlagCard flag key copy button', () => {
  beforeEach(() => {
    Object.defineProperty(navigator, 'clipboard', {
      value: { writeText: vi.fn().mockResolvedValue(undefined) },
      configurable: true,
    });
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('offers a copy control named after the flag key', () => {
    renderCard();

    expect(
      screen.getByRole('button', { name: `Copy flag key ${flag.key}` }),
    ).toBeInTheDocument();
  });

  it('copies the key and confirms it', async () => {
    renderCard();
    const button = screen.getByRole('button', { name: `Copy flag key ${flag.key}` });

    fireEvent.click(button);

    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalledWith(flag.key));
    await waitFor(() => expect(button).toHaveAttribute('data-copied', 'true'));
  });

  it('does not claim a copy when the clipboard is denied', async () => {
    vi.mocked(navigator.clipboard.writeText).mockRejectedValue(new Error('denied'));
    renderCard();
    const button = screen.getByRole('button', { name: `Copy flag key ${flag.key}` });

    fireEvent.click(button);

    await waitFor(() => expect(navigator.clipboard.writeText).toHaveBeenCalled());
    expect(button).toHaveAttribute('data-copied', 'false');
  });
});
