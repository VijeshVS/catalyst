import { fireEvent, render, screen, waitFor } from '@testing-library/react';
import { describe, expect, it, vi } from 'vitest';

import type { Flag, TargetingRule } from '../api';
import { RuleBuilder } from '../components/RuleBuilder';
import {
  defaultCondition,
  findAttribute,
  operatorsForAttribute,
  previewConditionMatch,
  previewRuleMatch,
} from '../lib/attributeCatalog';
import {
  coerceAttributeValue,
  draftFromRule,
  formatAttributeInput,
  operatorNeedsValue,
  parseAttributeInput,
  toRuleConditions,
  validateRuleDraft,
} from '../lib/targeting';
import type { ProjectData } from '../workspace/useProject';

const FLAG: Flag = {
  id: 'flag-1',
  project_id: 'project-1',
  key: 'ai-assistant',
  name: 'AI Assistant',
  default_value: false,
  archived: false,
  created_at: '2026-01-01T00:00:00Z',
  states: [],
  rules: [],
};

const INTERNAL_RULE: TargetingRule = {
  id: 'rule-internal',
  env: 'dev',
  priority: 0,
  conditions: [{ attr: 'email', op: 'ends_with', value: '@acme.com' }],
  serve: true,
};

const BETA_RULE: TargetingRule = {
  id: 'rule-beta',
  env: 'dev',
  priority: 1,
  conditions: [
    { attr: 'plan', op: 'in', value: ['pro', 'enterprise'] },
    { attr: 'version', op: 'greater_than_or_equal', value: 3 },
  ],
  serve: false,
};

function projectDataWith(overrides: Partial<ProjectData> = {}): ProjectData {
  return {
    flags: [FLAG],
    environments: [],
    activeEnv: 'dev',
    loading: false,
    error: null,
    playground: {},
    setActiveEnv: vi.fn(),
    refresh: vi.fn(async () => {}),
    toggleKillSwitch: vi.fn(async () => {}),
    updateRollout: vi.fn(async () => {}),
    createFlag: vi.fn(),
    createEnvironment: vi.fn(),
    createRule: vi.fn(async () => INTERNAL_RULE),
    updateRule: vi.fn(async () => INTERNAL_RULE),
    deleteRule: vi.fn(async () => {}),
    moveRule: vi.fn(async () => {}),
    evaluate: vi.fn(async () => {}),
    setPlaygroundAttributes: vi.fn(),
    stateFor: () => ({ env: 'dev', enabled: true, percentage: 0, version: 1 }),
    rulesFor: () => [],
    ...overrides,
  } as unknown as ProjectData;
}

function openBuilder(projectData: ProjectData) {
  render(<RuleBuilder flag={FLAG} projectData={projectData} />);
  fireEvent.click(screen.getByRole('button', { name: /targeting rules/i }));
}

describe('targeting value helpers', () => {
  it('coerces booleans, numbers, and leaves other text alone', () => {
    expect(coerceAttributeValue('true')).toBe(true);
    expect(coerceAttributeValue(' false ')).toBe(false);
    expect(coerceAttributeValue('3')).toBe(3);
    expect(coerceAttributeValue('2.5')).toBe(2.5);
    expect(coerceAttributeValue('@acme.com')).toBe('@acme.com');
    expect(coerceAttributeValue('')).toBe('');
  });

  it('splits list operators into a coerced array', () => {
    expect(
      toRuleConditions({
        serve: true,
        conditions: [{ attr: 'plan', op: 'in', value: 'pro, enterprise, 3' }],
      }),
    ).toEqual([{ attr: 'plan', op: 'in', value: ['pro', 'enterprise', 3] }]);
  });

  it('omits the value for presence operators', () => {
    expect(operatorNeedsValue('exists')).toBe(false);
    expect(operatorNeedsValue('not_exists')).toBe(false);
    expect(
      toRuleConditions({ serve: false, conditions: [{ attr: 'trial', op: 'exists', value: '' }] }),
    ).toEqual([{ attr: 'trial', op: 'exists' }]);
  });

  it('rejects drafts without an attribute or a required value', () => {
    expect(validateRuleDraft({ serve: true, conditions: [] })).toMatch(/at least one condition/i);
    expect(
      validateRuleDraft({ serve: true, conditions: [{ attr: ' ', op: 'equals', value: 'x' }] }),
    ).toMatch(/attribute/i);
    expect(
      validateRuleDraft({ serve: true, conditions: [{ attr: 'email', op: 'ends_with', value: '' }] }),
    ).toMatch(/value/i);
    // A presence operator legitimately has no value.
    expect(
      validateRuleDraft({ serve: true, conditions: [{ attr: 'trial', op: 'exists', value: '' }] }),
    ).toBeNull();
  });

  it('round-trips a saved rule into an editable draft', () => {
    expect(draftFromRule(BETA_RULE)).toEqual({
      serve: false,
      conditions: [
        { attr: 'plan', op: 'in', value: 'pro, enterprise' },
        { attr: 'version', op: 'greater_than_or_equal', value: '3' },
      ],
    });
  });

  it('parses playground attributes from key=value lines or JSON', () => {
    expect(parseAttributeInput('email=dev@acme.com\nplan=pro\nbeta=true')).toEqual({
      email: 'dev@acme.com',
      plan: 'pro',
      beta: true,
    });
    expect(parseAttributeInput('{"role": "admin", "seats": 12}')).toEqual({
      role: 'admin',
      seats: 12,
    });
    expect(parseAttributeInput('   ')).toEqual({});
    expect(formatAttributeInput({ email: 'dev@acme.com', beta: true })).toBe(
      'email=dev@acme.com\nbeta=true',
    );
  });
});

describe('attribute catalogue and match preview', () => {
  it('exposes typed metadata for known attributes', () => {
    expect(findAttribute('country')?.kind).toBe('enum');
    expect(findAttribute('seats')?.kind).toBe('number');
    expect(findAttribute('is_beta')?.kind).toBe('boolean');
    expect(findAttribute('app_version')?.kind).toBe('version');
    expect(findAttribute('email')?.kind).toBe('email');
    expect(findAttribute('nope')).toBeUndefined();
  });

  it('suggests sensible operators per attribute', () => {
    expect(operatorsForAttribute('seats')).toContain('greater_than_or_equal');
    expect(operatorsForAttribute('seats')).not.toContain('contains');
    expect(operatorsForAttribute('is_beta')).not.toContain('greater_than');
  });

  it('defaults a new condition to a preset, not a blank', () => {
    expect(defaultCondition()).toEqual({ attr: 'email', op: 'ends_with', value: 'alice@acme.com' });
  });

  it('mirrors the evaluator for presence operators and missing attributes', () => {
    expect(previewConditionMatch({ attr: 'is_beta', op: 'exists' }, {})).toBe(false);
    expect(previewConditionMatch({ attr: 'is_beta', op: 'exists' }, { is_beta: false })).toBe(true);
    expect(previewConditionMatch({ attr: 'is_beta', op: 'not_exists' }, {})).toBe(true);
    // A missing attribute makes any other condition false.
    expect(previewConditionMatch({ attr: 'plan', op: 'equals', value: 'pro' }, {})).toBe(false);
  });

  it('compares versions segment by segment', () => {
    expect(previewConditionMatch({ attr: 'app_version', op: 'greater_than_or_equal', value: '3.2' }, { app_version: '3.10.0' })).toBe(true);
    expect(previewConditionMatch({ attr: 'app_version', op: 'greater_than_or_equal', value: '3.10' }, { app_version: '3.9.0' })).toBe(false);
  });

  it('treats a string value as a list for in/not_in', () => {
    expect(previewConditionMatch({ attr: 'plan', op: 'in', value: 'pro,enterprise' }, { plan: 'pro' })).toBe(true);
    expect(previewConditionMatch({ attr: 'plan', op: 'not_in', value: ['free'] }, { plan: 'pro' })).toBe(true);
  });

  it('requires every condition in a rule to match', () => {
    const conditions = [
      { attr: 'email', op: 'ends_with' as const, value: '@acme.com' },
      { attr: 'plan', op: 'in' as const, value: ['pro'] },
    ];
    expect(previewRuleMatch(conditions, { email: 'a@acme.com', plan: 'pro' })).toBe(true);
    expect(previewRuleMatch(conditions, { email: 'a@acme.com', plan: 'free' })).toBe(false);
    expect(previewRuleMatch(conditions, { email: 'a@acme.com' })).toBe(false);
  });
});

describe('RuleBuilder', () => {
  it('starts collapsed and summarises the active environment', () => {
    render(<RuleBuilder flag={FLAG} projectData={projectDataWith()} />);
    const disclosure = screen.getByRole('button', { name: /targeting rules/i });
    expect(disclosure).toHaveAttribute('aria-expanded', 'false');
    expect(screen.getByText('DEV')).toBeInTheDocument();
    expect(screen.getByText('No rules')).toBeInTheDocument();
    expect(screen.queryByText(/Rules are checked in priority order/)).not.toBeInTheDocument();
  });

  it('asks for playground context before it can preview', () => {
    openBuilder(projectDataWith());
    expect(screen.getByText(/add attributes in the playground below/i)).toBeInTheDocument();
  });

  it('shows which rule wins for the current playground context', () => {
    const projectData = projectDataWith({
      rulesFor: () => [INTERNAL_RULE, BETA_RULE],
      playground: { 'ai-assistant': { userId: 'u1', attributes: { email: 'dev@acme.com' } } },
    });
    openBuilder(projectData);

    expect(screen.getAllByText('matches').length).toBeGreaterThan(0);
    expect(screen.getByText(/first match wins: rule #1 serves true/i)).toBeInTheDocument();
  });

  it('falls back to rollout when nothing matches the context', () => {
    const projectData = projectDataWith({
      rulesFor: () => [INTERNAL_RULE],
      playground: { 'ai-assistant': { userId: 'u1', attributes: { country: 'IN' } } },
    });
    openBuilder(projectData);
    expect(screen.getByText(/nothing matches, so the percentage rollout/i)).toBeInTheDocument();
  });

  it('lists existing rules in priority order with their served value', () => {
    const projectData = projectDataWith({ rulesFor: () => [INTERNAL_RULE, BETA_RULE] });
    openBuilder(projectData);

    expect(screen.getByText('2 rules')).toBeInTheDocument();
    expect(screen.getByText('Rule #1')).toBeInTheDocument();
    expect(screen.getByText('Rule #2')).toBeInTheDocument();
    expect(screen.getByText('serve true')).toBeInTheDocument();
    expect(screen.getByText('serve false')).toBeInTheDocument();
    expect(screen.getByText('@acme.com')).toBeInTheDocument();
    expect(screen.getByText('pro, enterprise')).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Move rule 1 up' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Move rule 2 down' })).toBeDisabled();
  });

  it('seeds a new condition from the catalogue instead of a blank field', () => {
    openBuilder(projectDataWith());
    fireEvent.click(screen.getByRole('button', { name: /add targeting rule/i }));

    // The row arrives pre-filled with a sensible preset, so nothing must be typed.
    expect(screen.getByLabelText('Attribute')).toHaveValue('email');
    expect(screen.getByLabelText('Operator')).toHaveValue('ends_with');
    expect(screen.getByLabelText('Value')).toHaveValue('alice@acme.com');
  });

  it('creates a rule by picking attribute, operator, and value', async () => {
    const createRule = vi.fn(async () => INTERNAL_RULE);
    openBuilder(projectDataWith({ createRule }));

    fireEvent.click(screen.getByRole('button', { name: /add targeting rule/i }));
    fireEvent.change(screen.getByLabelText('Attribute'), { target: { value: 'country' } });
    fireEvent.change(screen.getByLabelText('Operator'), { target: { value: 'in' } });
    // 'IN' is seeded from the example; add 'US' by clicking a suggestion chip.
    expect(screen.getByRole('button', { name: 'Remove IN' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'US' }));
    fireEvent.click(screen.getByRole('button', { name: 'Create rule' }));

    await waitFor(() => {
      expect(createRule).toHaveBeenCalledWith(FLAG, {
        conditions: [{ attr: 'country', op: 'in', value: ['IN', 'US'] }],
        serve: true,
      });
    });
  });

  it('offers a closed option list for enum attributes', () => {
    openBuilder(projectDataWith());
    fireEvent.click(screen.getByRole('button', { name: /add targeting rule/i }));
    fireEvent.change(screen.getByLabelText('Attribute'), { target: { value: 'plan' } });

    const value = screen.getByLabelText('Value') as HTMLSelectElement;
    expect(value.tagName).toBe('SELECT');
    const options = [...value.options].map((option) => option.value);
    expect(options).toEqual(['', 'free', 'trial', 'starter', 'pro', 'enterprise']);
  });

  it('uses a True/False toggle for boolean attributes', async () => {
    const createRule = vi.fn(async () => INTERNAL_RULE);
    openBuilder(projectDataWith({ createRule }));

    fireEvent.click(screen.getByRole('button', { name: /add targeting rule/i }));
    fireEvent.change(screen.getByLabelText('Attribute'), { target: { value: 'is_beta' } });
    fireEvent.click(screen.getByRole('button', { name: 'false' }));
    fireEvent.click(screen.getByRole('button', { name: 'Create rule' }));

    await waitFor(() => {
      expect(createRule).toHaveBeenCalledWith(FLAG, {
        conditions: [{ attr: 'is_beta', op: 'equals', value: false }],
        serve: true,
      });
    });
  });

  it('only offers operators that suit the chosen attribute', () => {
    openBuilder(projectDataWith());
    fireEvent.click(screen.getByRole('button', { name: /add targeting rule/i }));
    fireEvent.change(screen.getByLabelText('Attribute'), { target: { value: 'app_version' } });

    const ops = [...(screen.getByLabelText('Operator') as HTMLSelectElement).options].map((o) => o.value);
    expect(ops).toContain('greater_than_or_equal');
    expect(ops).not.toContain('contains');
  });

  it('swaps to a token input for list operators', () => {
    openBuilder(projectDataWith());
    fireEvent.click(screen.getByRole('button', { name: /add targeting rule/i }));
    fireEvent.change(screen.getByLabelText('Attribute'), { target: { value: 'plan' } });
    fireEvent.change(screen.getByLabelText('Operator'), { target: { value: 'in' } });

    // Selecting `plan` seeds the first enum option as a token.
    expect(screen.getByRole('button', { name: 'Remove pro' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'starter' }));
    expect(screen.getByRole('button', { name: 'Remove starter' })).toBeInTheDocument();
    fireEvent.click(screen.getByRole('button', { name: 'Remove pro' }));
    expect(screen.queryByRole('button', { name: 'Remove pro' })).not.toBeInTheDocument();
  });

  it('falls back to a free-text attribute via Custom attribute', () => {
    openBuilder(projectDataWith());
    fireEvent.click(screen.getByRole('button', { name: /add targeting rule/i }));
    fireEvent.change(screen.getByLabelText('Attribute'), { target: { value: '__custom__' } });

    const attr = screen.getByLabelText('Attribute');
    expect(attr.tagName).toBe('INPUT');
    fireEvent.change(attr, { target: { value: 'my_tenant_tier' } });
    expect(screen.getByText(/custom attribute evaluated against the request context/i)).toBeInTheDocument();
  });

  it('blocks saving until every condition is complete', () => {
    const createRule = vi.fn(async () => INTERNAL_RULE);
    openBuilder(projectDataWith({ createRule }));

    fireEvent.click(screen.getByRole('button', { name: /add targeting rule/i }));
    fireEvent.change(screen.getByLabelText('Value'), { target: { value: '' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create rule' }));

    expect(createRule).not.toHaveBeenCalled();
    expect(screen.getByText(/provide a value for/i)).toBeInTheDocument();
  });

  it('adds and removes conditions within one rule', () => {
    const createRule = vi.fn(async () => INTERNAL_RULE);
    openBuilder(projectDataWith({ createRule }));

    fireEvent.click(screen.getByRole('button', { name: /add targeting rule/i }));
    fireEvent.click(screen.getByRole('button', { name: /add condition/i }));
    expect(screen.getAllByLabelText('Attribute')).toHaveLength(2);

    // The last row can be removed, the only remaining one cannot.
    expect(screen.getByRole('button', { name: 'Remove condition 1' })).toBeEnabled();
    fireEvent.click(screen.getByRole('button', { name: 'Remove condition 2' }));
    expect(screen.getAllByLabelText('Attribute')).toHaveLength(1);
    expect(screen.getByRole('button', { name: 'Remove condition 1' })).toBeDisabled();
    expect(createRule).not.toHaveBeenCalled();
  });

  it('toggles the served value and saves it with the conditions', async () => {
    const updateRule = vi.fn(async () => INTERNAL_RULE);
    openBuilder(projectDataWith({ rulesFor: () => [INTERNAL_RULE], updateRule }));

    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    fireEvent.click(screen.getByRole('button', { name: 'False' }));
    fireEvent.click(screen.getByRole('button', { name: 'Save rule' }));

    await waitFor(() => {
      expect(updateRule).toHaveBeenCalledWith(FLAG, INTERNAL_RULE, {
        conditions: [{ attr: 'email', op: 'ends_with', value: '@acme.com' }],
        serve: false,
      });
    });
  });

  it('discards an edit without calling the API', () => {
    const updateRule = vi.fn(async () => INTERNAL_RULE);
    openBuilder(projectDataWith({ rulesFor: () => [INTERNAL_RULE], updateRule }));

    fireEvent.click(screen.getByRole('button', { name: 'Edit' }));
    fireEvent.change(screen.getByLabelText('Value'), { target: { value: '@other.com' } });
    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));

    expect(updateRule).not.toHaveBeenCalled();
    expect(screen.queryByLabelText('Value')).not.toBeInTheDocument();
  });

  it('requires a confirmation before deleting a rule', async () => {
    const deleteRule = vi.fn(async () => {});
    openBuilder(projectDataWith({ rulesFor: () => [INTERNAL_RULE], deleteRule }));

    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    expect(deleteRule).not.toHaveBeenCalled();

    fireEvent.click(screen.getByRole('button', { name: 'Confirm' }));
    await waitFor(() => expect(deleteRule).toHaveBeenCalledWith(FLAG, INTERNAL_RULE));
  });

  it('cancels a pending deletion', () => {
    const deleteRule = vi.fn(async () => {});
    openBuilder(projectDataWith({ rulesFor: () => [INTERNAL_RULE], deleteRule }));

    fireEvent.click(screen.getByRole('button', { name: 'Delete' }));
    fireEvent.click(screen.getByRole('button', { name: 'Keep' }));

    expect(deleteRule).not.toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Delete' })).toBeInTheDocument();
  });

  it('moves a rule up or down through the priority order', () => {
    const moveRule = vi.fn(async () => {});
    openBuilder(projectDataWith({ rulesFor: () => [INTERNAL_RULE, BETA_RULE], moveRule }));

    fireEvent.click(screen.getByRole('button', { name: 'Move rule 2 up' }));
    expect(moveRule).toHaveBeenCalledWith(FLAG, BETA_RULE, -1);

    fireEvent.click(screen.getByRole('button', { name: 'Move rule 1 down' }));
    expect(moveRule).toHaveBeenCalledWith(FLAG, INTERNAL_RULE, 1);
  });

  it('surfaces an API failure without losing the draft', async () => {
    const createRule = vi.fn(async () => {
      throw new Error('Flag is archived');
    });
    openBuilder(projectDataWith({ createRule }));

    fireEvent.click(screen.getByRole('button', { name: /add targeting rule/i }));
    fireEvent.change(screen.getByLabelText('Attribute'), { target: { value: 'country' } });
    fireEvent.change(screen.getByLabelText('Operator'), { target: { value: 'equals' } });
    fireEvent.change(screen.getByLabelText('Value'), { target: { value: 'IN' } });
    fireEvent.click(screen.getByRole('button', { name: 'Create rule' }));

    expect(await screen.findByText('Flag is archived')).toBeInTheDocument();
    expect(screen.getByLabelText('Attribute')).toHaveValue('country');
  });
});
