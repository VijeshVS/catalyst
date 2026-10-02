import { useState } from 'react';

import { getErrorMessage } from '../api';
import type { Flag, RuleCondition, RuleOperator, TargetingRule } from '../api';
import {
  CUSTOM_ATTRIBUTE,
  attributeGroups,
  attributeKind,
  attributeLabel,
  attributeOptions,
  exampleValueFor,
  findAttribute,
  operatorsForAttribute,
  previewConditionMatch,
  previewRuleMatch,
} from '../lib/attributeCatalog';
import {
  MAX_RULE_CONDITIONS,
  RULE_OPERATORS,
  draftFromRule,
  emptyCondition,
  emptyRuleDraft,
  formatConditionValue,
  isListOperator,
  joinListTokens,
  operatorLabel,
  operatorNeedsValue,
  splitListTokens,
  toRuleConditions,
  validateRuleDraft,
} from '../lib/targeting';
import type { ConditionDraft, RuleDraft } from '../lib/targeting';
import type { ProjectData } from '../workspace/useProject';

interface RuleBuilderProps {
  flag: Flag;
  projectData: ProjectData;
}

function serveClass(serve: boolean): string {
  return serve ? 'serve-true' : 'serve-false';
}

const OPERATOR_LABELS = new Map(RULE_OPERATORS.map((option) => [option.value, option.label]));

/** Picks a sensible default operator for the attribute that was just chosen. */
function preferredOperator(attr: string, current: RuleOperator): RuleOperator {
  if (attr === CUSTOM_ATTRIBUTE) return current;
  const allowed = operatorsForAttribute(attr);
  return allowed.includes(current) ? current : allowed[0];
}

/**
 * Token input for `in` / `not_in`: values are added with Enter or by clicking a
 * suggestion, so a list is built by picking rather than by typing separators.
 */
function TokenValueInput({
  id,
  tokens,
  suggestions,
  placeholder,
  onChange,
}: {
  id: string;
  tokens: string[];
  suggestions: readonly string[];
  placeholder: string;
  onChange: (next: string) => void;
}) {
  const [entry, setEntry] = useState('');
  const remaining = suggestions.filter((option) => !tokens.includes(option));

  const add = (value: string) => {
    const trimmed = value.trim();
    if (!trimmed || tokens.includes(trimmed)) {
      setEntry('');
      return;
    }
    onChange(joinListTokens([...tokens, trimmed]));
    setEntry('');
  };

  return (
    <div className="rule-token-field">
      <div className="rule-token-chips">
        {tokens.map((token) => (
          <span key={token} className="rule-token">
            {token}
            <button
              type="button"
              aria-label={`Remove ${token}`}
              onClick={() => onChange(joinListTokens(tokens.filter((entry2) => entry2 !== token)))}
            >
              ×
            </button>
          </span>
        ))}
        <input
          id={id}
          className="rule-token-input"
          value={entry}
          placeholder={tokens.length === 0 ? placeholder : 'Add another…'}
          autoComplete="off"
          onChange={(event) => setEntry(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' || event.key === ',') {
              event.preventDefault();
              add(entry);
            } else if (event.key === 'Backspace' && entry === '' && tokens.length > 0) {
              onChange(joinListTokens(tokens.slice(0, -1)));
            }
          }}
        />
      </div>
      {remaining.length > 0 && (
        <div className="rule-token-suggestions">
          {remaining.slice(0, 8).map((option) => (
            <button key={option} type="button" className="rule-token-suggestion" onClick={() => add(option)}>
              <span aria-hidden="true">+</span> {option}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

/** Value control chosen from the attribute's kind, so nothing needs typing. */
function ValueControl({
  condition,
  id,
  onChange,
}: {
  condition: ConditionDraft;
  id: string;
  onChange: (next: ConditionDraft) => void;
}) {
  if (!operatorNeedsValue(condition.op)) {
    return (
      <p className="rule-value-none" id={id}>
        No value needed
      </p>
    );
  }

  const kind = attributeKind(condition.attr);
  const options = attributeOptions(condition.attr);

  if (isListOperator(condition.op)) {
    return (
      <TokenValueInput
        id={id}
        tokens={splitListTokens(condition.value)}
        suggestions={options}
        placeholder="Add a value…"
        onChange={(value) => onChange({ ...condition, value })}
      />
    );
  }

  if (kind === 'boolean') {
    return (
      <div className="rule-bool-field" role="group" aria-label={`Value for ${condition.attr}`}>
        {['true', 'false'].map((option) => (
          <button
            key={option}
            type="button"
            id={option === 'true' ? id : undefined}
            className={`rule-serve-option ${option === 'true' ? 'serve-true' : 'serve-false'} ${
              condition.value === option ? 'active' : ''
            }`}
            aria-pressed={condition.value === option}
            onClick={() => onChange({ ...condition, value: option })}
          >
            {option}
          </button>
        ))}
      </div>
    );
  }

  if (kind === 'enum' && options.length > 0) {
    return (
      <select
        id={id}
        className="form-input"
        value={options.includes(condition.value) ? condition.value : ''}
        onChange={(event) => onChange({ ...condition, value: event.target.value })}
      >
        <option value="">Select a value…</option>
        {options.map((option) => (
          <option key={option} value={option}>{option}</option>
        ))}
      </select>
    );
  }

  if (kind === 'number') {
    return (
      <input
        id={id}
        className="form-input"
        type="number"
        inputMode="decimal"
        value={condition.value}
        placeholder="10"
        onChange={(event) => onChange({ ...condition, value: event.target.value })}
      />
    );
  }

  return (
    <input
      id={id}
      className="form-input"
      value={condition.value}
      placeholder={findAttribute(condition.attr)?.placeholder ?? 'value'}
      autoComplete="off"
      onChange={(event) => onChange({ ...condition, value: event.target.value })}
    />
  );
}

function ConditionRow({
  condition,
  index,
  idPrefix,
  canRemove,
  context,
  onChange,
  onRemove,
}: {
  condition: ConditionDraft;
  index: number;
  idPrefix: string;
  canRemove: boolean;
  context: Record<string, unknown>;
  onChange: (next: ConditionDraft) => void;
  onRemove: () => void;
}) {
  const isCustom = condition.attr === CUSTOM_ATTRIBUTE || !findAttribute(condition.attr);
  const spec = findAttribute(condition.attr);
  const groups = attributeGroups();
  const valueId = `${idPrefix}-value-${index}`;
  const attrId = `${idPrefix}-attr-${index}`;
  const opId = `${idPrefix}-op-${index}`;
  const needsValue = operatorNeedsValue(condition.op);
  const matches = needsValue && condition.value !== '' && previewConditionMatch(
    { attr: condition.attr, op: condition.op, value: isListOperator(condition.op) ? splitListTokens(condition.value) : condition.value },
    context,
  );

  return (
    <div className="rule-condition-row">
      <div className="rule-condition-field">
        <label className="form-label" htmlFor={attrId}>Attribute</label>
        {isCustom ? (
          <input
            id={attrId}
            className="form-input"
            value={condition.attr === CUSTOM_ATTRIBUTE ? '' : condition.attr}
            placeholder="custom_attribute"
            autoComplete="off"
            onChange={(event) => onChange({ ...condition, attr: event.target.value })}
          />
        ) : (
          <select
            id={attrId}
            className="form-input"
            value={condition.attr}
            onChange={(event) => {
              const attr = event.target.value;
              const op = preferredOperator(attr, condition.op);
              const keepValue = attr === condition.attr;
              onChange({
                ...condition,
                attr,
                op,
                value: keepValue ? condition.value : exampleValueFor(attr, op),
              });
            }}
          >
            {groups.map((group) => (
              <optgroup key={group.group} label={group.group}>
                {group.specs.map((entry) => (
                  <option key={entry.key} value={entry.key}>{entry.label}</option>
                ))}
              </optgroup>
            ))}
            <option value={CUSTOM_ATTRIBUTE}>Custom attribute…</option>
          </select>
        )}
        {isCustom && (
          <button
            type="button"
            className="text-button rule-custom-back"
            onClick={() =>
              onChange({ ...condition, attr: 'email', op: preferredOperator('email', condition.op), value: exampleValueFor('email', condition.op) })
            }
          >
            Back to presets
          </button>
        )}
      </div>

      <div className="rule-condition-field rule-condition-operator">
        <label className="form-label" htmlFor={opId}>Operator</label>
        <select
          id={opId}
          className="form-input"
          value={condition.op}
          onChange={(event) => {
            const op = event.target.value as RuleOperator;
            onChange({
              ...condition,
              op,
              value: operatorNeedsValue(op) && condition.value === '' ? exampleValueFor(condition.attr, op) : condition.value,
            });
          }}
        >
          {(isCustom ? RULE_OPERATORS.map((o) => o.value) : operatorsForAttribute(condition.attr)).map((op) => (
            <option key={op} value={op}>{OPERATOR_LABELS.get(op) ?? op}</option>
          ))}
        </select>
      </div>

      <div className="rule-condition-field">
        <label className="form-label" htmlFor={valueId}>Value</label>
        <ValueControl condition={condition} id={valueId} onChange={onChange} />
        {needsValue && (
          <span className={`rule-condition-state ${matches ? 'hit' : 'miss'}`}>
            {matches ? 'Matches context' : 'Does not match context'}
          </span>
        )}
      </div>

      <button
        type="button"
        className="icon-button rule-condition-remove"
        onClick={onRemove}
        disabled={!canRemove}
        aria-label={`Remove condition ${index + 1}`}
      >
        ×
      </button>
      <span className="rule-condition-hint">
        {spec ? spec.description : 'Custom attribute evaluated against the request context.'}
      </span>
    </div>
  );
}

/** Ordered read-out of how the current context resolves against every rule. */
function MatchPreview({
  rules,
  draft,
  context,
  activeEnv,
}: {
  rules: TargetingRule[];
  draft: RuleDraft | null;
  context: Record<string, unknown>;
  activeEnv: string;
}) {
  const hasContext = Object.keys(context).length > 0;
  const saved = rules.map((rule, index) => ({
    id: rule.id,
    label: rule.name || `Rule #${index + 1}`,
    serve: rule.serve,
    conditions: rule.conditions,
  }));
  const pending = draft
    ? [
        {
          id: '__draft__' as const,
          label: draft.name.trim() || 'New rule',
          serve: draft.serve,
          conditions: toRuleConditions(draft),
        },
      ]
    : [];
  const all = [...saved, ...pending];
  const winner = hasContext ? all.find((entry) => previewRuleMatch(entry.conditions, context)) : undefined;

  return (
    <div className="rule-preview">
      <div className="rule-preview-header">
        <span className="rule-preview-title">Match preview</span>
        <span className="rule-preview-env">{activeEnv.toUpperCase()}</span>
      </div>
      {!hasContext ? (
        <p className="rule-preview-hint">
          Add attributes in the playground below to see which rule wins for a real user.
        </p>
      ) : all.length === 0 ? (
        <p className="rule-preview-hint">
          No rules yet, so nobody is filtered out and the rollout decides on its own.
        </p>
      ) : (
        <>
          <ol className="rule-preview-list">
            {all.map((entry) => {
              const matched = previewRuleMatch(entry.conditions, context);
              return (
                <li
                  key={entry.id}
                  className={`rule-preview-item ${matched ? 'hit' : 'miss'} ${
                    winner?.id === entry.id ? 'winner' : ''
                  }`}
                >
                  <span className="rule-preview-marker" aria-hidden="true">
                    {matched ? '●' : '○'}
                  </span>
                  <span className="rule-preview-label">{entry.label}</span>
                  <span className="rule-preview-verdict">
                    {matched ? 'matches' : 'no match'}
                  </span>
                  {winner?.id === entry.id && (
                    <span className="rule-preview-serve">serves {entry.serve ? 'true' : 'false'}</span>
                  )}
                </li>
              );
            })}
          </ol>
          <p className="rule-preview-result">
            {winner
              ? `${winner.label} matched, so this user is in the audience. Inside the rollout it serves ${
                  winner.serve ? 'true' : 'false'
                }; outside it, the opposite.`
              : 'No rule matches, so this user is filtered out of the audience and gets false whatever the rollout is.'}
          </p>
        </>
      )}
    </div>
  );
}

function ConditionSummary({ condition }: { condition: RuleCondition }) {
  return (
    <li className="rule-summary-condition">
      <code className="rule-chip">{attributeLabel(condition.attr)}</code>
      <span className="rule-summary-operator">{operatorLabel(condition.op)}</span>
      {operatorNeedsValue(condition.op) && (
        <code className="rule-chip rule-chip-value">{formatConditionValue(condition.value)}</code>
      )}
    </li>
  );
}

function RuleEditor({
  draft,
  idPrefix,
  title,
  error,
  saving,
  saveLabel,
  onChange,
  onSave,
  onCancel,
  onAddCondition,
  onRemoveCondition,
  context,
}: {
  draft: RuleDraft;
  idPrefix: string;
  title: string;
  error: string | null;
  saving: boolean;
  saveLabel: string;
  context: Record<string, unknown>;
  onChange: (next: RuleDraft) => void;
  onSave: () => void;
  onCancel: () => void;
  onAddCondition: () => void;
  onRemoveCondition: (index: number) => void;
}) {
  const setCondition = (index: number, next: ConditionDraft) =>
    onChange({
      ...draft,
      conditions: draft.conditions.map((current, position) => (position === index ? next : current)),
    });

  return (
    <div className="rule-card editing">
      <div className="rule-card-header">
        <h4 className="rule-card-title">{title}</h4>
        <div className="rule-serve-toggle" role="group" aria-label="Value served when matched">
          <span className="rule-serve-label">Serve</span>
          <button
            type="button"
            className={`rule-serve-option ${serveClass(draft.serve)}`}
            aria-pressed={draft.serve}
            onClick={() => onChange({ ...draft, serve: true })}
          >
            True
          </button>
          <button
            type="button"
            className={`rule-serve-option ${serveClass(!draft.serve)}`}
            aria-pressed={!draft.serve}
            onClick={() => onChange({ ...draft, serve: false })}
          >
            False
          </button>
        </div>
      </div>

      <div className="form-group">
        <label className="form-label" htmlFor={`${idPrefix}-name`}>Rule label</label>
        <input
          id={`${idPrefix}-name`}
          className="form-input"
          type="text"
          maxLength={128}
          value={draft.name}
          onChange={(event) => onChange({ ...draft, name: event.target.value })}
          placeholder="e.g. Internal beta"
        />
        <p className="form-hint">Optional. Used to tell this rule apart from the others.</p>
      </div>

      <p className="rule-logic-note">
        Every condition must match (AND) for this rule to apply. Conditions are checked in order
        against the attributes you set in the playground.
      </p>

      <div className="rule-condition-list">
        {draft.conditions.map((condition, index) => (
          <ConditionRow
            key={index}
            idPrefix={idPrefix}
            condition={condition}
            index={index}
            context={context}
            canRemove={draft.conditions.length > 1}
            onChange={(next) => setCondition(index, next)}
            onRemove={() => onRemoveCondition(index)}
          />
        ))}
      </div>

      <div className="rule-card-footer">
        <button
          type="button"
          className="text-button"
          onClick={onAddCondition}
          disabled={draft.conditions.length >= MAX_RULE_CONDITIONS}
          title={
            draft.conditions.length >= MAX_RULE_CONDITIONS
              ? `A rule can hold at most ${MAX_RULE_CONDITIONS} conditions`
              : undefined
          }
        >
          <span aria-hidden="true">+</span> Add condition
        </button>
        <div className="rule-card-actions">
          <button type="button" className="btn-secondary" onClick={onCancel} disabled={saving}>
            Cancel
          </button>
          <button type="button" className="btn-primary" onClick={onSave} disabled={saving}>
            {saving ? 'Saving…' : saveLabel}
          </button>
        </div>
      </div>
      {error && <div className="form-error">{error}</div>}
    </div>
  );
}

export function RuleBuilder({ flag, projectData }: RuleBuilderProps) {
  const [open, setOpen] = useState(false);
  const [drafts, setDrafts] = useState<Record<string, RuleDraft>>({});
  const [newDraft, setNewDraft] = useState<RuleDraft | null>(null);
  const [confirmingDelete, setConfirmingDelete] = useState<string | null>(null);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const rules = projectData.rulesFor(flag);
  const idPrefix = `rule-${flag.key}`;
  // The same context the playground will send, so the preview reflects reality.
  const context = projectData.playground[flag.key]?.attributes ?? {};
  const editingCount = Object.keys(drafts).length + (newDraft ? 1 : 0);

  const setDraft = (ruleId: string, next: RuleDraft | null) =>
    setDrafts((previous) => {
      const updated = { ...previous };
      if (next) updated[ruleId] = next;
      else delete updated[ruleId];
      return updated;
    });

  const saveExisting = async (rule: TargetingRule) => {
    const draft = drafts[rule.id];
    if (!draft) return;
    const validationError = validateRuleDraft(draft);
    if (validationError) {
      setError(validationError);
      return;
    }
    setBusyId(rule.id);
    setError(null);
    try {
      await projectData.updateRule(flag, rule, {
        name: draft.name.trim(),
        conditions: toRuleConditions(draft),
        serve: draft.serve,
      });
      setDraft(rule.id, null);
    } catch (requestError) {
      setError(getErrorMessage(requestError, 'Unable to save targeting rule'));
    } finally {
      setBusyId(null);
    }
  };

  const saveNew = async () => {
    if (!newDraft) return;
    const validationError = validateRuleDraft(newDraft);
    if (validationError) {
      setError(validationError);
      return;
    }
    setBusyId('new');
    setError(null);
    try {
      await projectData.createRule(flag, {
        name: newDraft.name.trim(),
        conditions: toRuleConditions(newDraft),
        serve: newDraft.serve,
      });
      setNewDraft(null);
    } catch (requestError) {
      setError(getErrorMessage(requestError, 'Unable to create targeting rule'));
    } finally {
      setBusyId(null);
    }
  };

  const removeRule = async (rule: TargetingRule) => {
    setBusyId(rule.id);
    setError(null);
    try {
      await projectData.deleteRule(flag, rule);
      setDraft(rule.id, null);
      setConfirmingDelete(null);
    } catch (requestError) {
      setError(getErrorMessage(requestError, 'Unable to delete targeting rule'));
    } finally {
      setBusyId(null);
    }
  };

  const moveRule = async (rule: TargetingRule, direction: -1 | 1) => {
    setBusyId(rule.id);
    try {
      await projectData.moveRule(flag, rule, direction);
    } finally {
      setBusyId(null);
    }
  };

  return (
    <section className="rule-builder">
      <button
        type="button"
        className="rule-disclosure"
        aria-expanded={open}
        onClick={() => setOpen((previous) => !previous)}
      >
        <span className="rule-disclosure-caret" aria-hidden="true">{open ? '▾' : '▸'}</span>
        <span className="rule-disclosure-title">Targeting rules</span>
        <span className="rule-disclosure-env">{projectData.activeEnv.toUpperCase()}</span>
        <span className="rule-count">
          {rules.length === 0 ? 'No rules' : `${rules.length} rule${rules.length === 1 ? '' : 's'}`}
        </span>
      </button>

      {open && (
        <div className="rule-builder-body">
          <p className="rule-builder-intro">
            Rules are checked in priority order and the first rule whose conditions all match
            puts the user in the audience. If rules exist and none matched, the user is filtered
            out and gets <code>false</code>. The rollout then splits whoever is left.
          </p>

          <MatchPreview
            rules={rules}
            draft={newDraft}
            context={context}
            activeEnv={projectData.activeEnv}
          />

          {error && editingCount === 0 && <div className="form-error">{error}</div>}

          {rules.length === 0 && !newDraft && (
            <div className="rule-empty-state">
              <p>
                No targeting rules in <strong>{projectData.activeEnv}</strong>, so nobody is
                filtered out and the rollout alone decides who gets the feature.
              </p>
            </div>
          )}

          {rules.map((rule, index) => {
            const draft = drafts[rule.id];
            if (draft) {
              return (
                <RuleEditor
                  key={rule.id}
                  idPrefix={`${idPrefix}-${rule.id}`}
                  title={`Editing rule #${index + 1}`}
                  draft={draft}
                  context={context}
                  error={error}
                  saving={busyId === rule.id}
                  saveLabel="Save rule"
                  onChange={(next) => setDraft(rule.id, next)}
                  onSave={() => void saveExisting(rule)}
                  onCancel={() => {
                    setDraft(rule.id, null);
                    setError(null);
                  }}
                  onAddCondition={() =>
                    setDraft(rule.id, {
                      ...draft,
                      conditions: [...draft.conditions, emptyCondition()],
                    })
                  }
                  onRemoveCondition={(position) =>
                    setDraft(rule.id, {
                      ...draft,
                      conditions: draft.conditions.filter((_, current) => current !== position),
                    })
                  }
                />
              );
            }

            const isConfirming = confirmingDelete === rule.id;
            const busy = busyId === rule.id;
            return (
              <div key={rule.id} className="rule-card">
                <div className="rule-card-header">
                  <h4 className="rule-card-title">
                    <span className="rule-priority">{rule.name || `Rule #${index + 1}`}</span>
                    <span className={`rule-serve-badge ${serveClass(rule.serve)}`}>
                      serve {rule.serve ? 'true' : 'false'}
                    </span>
                  </h4>
                  <div className="rule-actions">
                    <button
                      type="button"
                      className="icon-button"
                      aria-label={`Move rule ${index + 1} up`}
                      disabled={index === 0 || busy}
                      onClick={() => void moveRule(rule, -1)}
                    >
                      ↑
                    </button>
                    <button
                      type="button"
                      className="icon-button"
                      aria-label={`Move rule ${index + 1} down`}
                      disabled={index === rules.length - 1 || busy}
                      onClick={() => void moveRule(rule, 1)}
                    >
                      ↓
                    </button>
                    <button
                      type="button"
                      className="btn-secondary rule-edit-btn"
                      onClick={() => setDraft(rule.id, draftFromRule(rule))}
                    >
                      Edit
                    </button>
                    {isConfirming ? (
                      <>
                        <button
                          type="button"
                          className="btn-revoke"
                          disabled={busy}
                          onClick={() => void removeRule(rule)}
                        >
                          {busy ? 'Deleting…' : 'Confirm'}
                        </button>
                        <button
                          type="button"
                          className="btn-secondary"
                          disabled={busy}
                          onClick={() => setConfirmingDelete(null)}
                        >
                          Keep
                        </button>
                      </>
                    ) : (
                      <button
                        type="button"
                        className="btn-revoke"
                        onClick={() => setConfirmingDelete(rule.id)}
                      >
                        Delete
                      </button>
                    )}
                  </div>
                </div>

                <ul className="rule-summary-list">
                  {rule.conditions.map((condition, position) => (
                    <ConditionSummary key={`${condition.attr}-${position}`} condition={condition} />
                  ))}
                </ul>
              </div>
            );
          })}

          {newDraft && (
            <RuleEditor
              idPrefix={`${idPrefix}-new`}
              title="New targeting rule"
              draft={newDraft}
              context={context}
              error={error}
              saving={busyId === 'new'}
              saveLabel="Create rule"
              onChange={setNewDraft}
              onSave={() => void saveNew()}
              onCancel={() => {
                setNewDraft(null);
                setError(null);
              }}
              onAddCondition={() =>
                setNewDraft({ ...newDraft, conditions: [...newDraft.conditions, emptyCondition()] })
              }
              onRemoveCondition={(position) =>
                setNewDraft({
                  ...newDraft,
                  conditions: newDraft.conditions.filter((_, current) => current !== position),
                })
              }
            />
          )}

          {!newDraft && (
            <button
              type="button"
              className="btn-gold-outline rule-add-button"
              onClick={() => {
                setNewDraft(emptyRuleDraft());
                setError(null);
              }}
            >
              <span aria-hidden="true">+</span> Add targeting rule
            </button>
          )}
        </div>
      )}
    </section>
  );
}
