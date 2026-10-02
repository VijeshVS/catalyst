import type { RuleCondition, RuleOperator } from '../api';

import { defaultCondition } from './attributeCatalog';

export interface OperatorOption {
  value: RuleOperator;
  label: string;
  hint: string;
}

/**
 * Operator catalogue for the rule builder. Labels are written for humans while
 * `value` always carries the canonical name the API expects.
 */
export const RULE_OPERATORS: OperatorOption[] = [
  { value: 'equals', label: 'equals', hint: 'Exact, case-sensitive match' },
  { value: 'not_equals', label: 'does not equal', hint: 'Exact, case-sensitive mismatch' },
  { value: 'in', label: 'is one of', hint: 'Comma-separated list, e.g. pro,enterprise' },
  { value: 'not_in', label: 'is not one of', hint: 'Comma-separated list, e.g. free,trial' },
  { value: 'contains', label: 'contains', hint: 'Case-insensitive substring' },
  { value: 'starts_with', label: 'starts with', hint: 'Case-insensitive prefix' },
  { value: 'ends_with', label: 'ends with', hint: 'Case-insensitive suffix' },
  { value: 'greater_than', label: '>', hint: 'Numeric comparison' },
  { value: 'greater_than_or_equal', label: '>=', hint: 'Numeric comparison' },
  { value: 'less_than', label: '<', hint: 'Numeric comparison' },
  { value: 'less_than_or_equal', label: '<=', hint: 'Numeric comparison' },
  { value: 'exists', label: 'is present', hint: 'Attribute exists, value ignored' },
  { value: 'not_exists', label: 'is missing', hint: 'Attribute is absent, value ignored' },
];

const OPERATOR_LABELS = new Map(RULE_OPERATORS.map((option) => [option.value, option.label]));

export function operatorLabel(op: RuleOperator): string {
  return OPERATOR_LABELS.get(op) ?? op;
}

export function operatorHint(op: RuleOperator): string {
  return RULE_OPERATORS.find((option) => option.value === op)?.hint ?? '';
}

export function operatorNeedsValue(op: RuleOperator): boolean {
  return op !== 'exists' && op !== 'not_exists';
}

/**
 * Converts a raw text value into the JSON type the evaluator compares against.
 * Booleans and numbers are lifted so a rule typed as `plan > 3` matches a
 * numeric attribute, and the playground uses the same coercion for the context
 * attributes it sends.
 */
export function coerceAttributeValue(raw: string): unknown {
  const trimmed = raw.trim();
  if (trimmed === '') return '';
  if (trimmed === 'true') return true;
  if (trimmed === 'false') return false;
  if (trimmed === 'null') return null;
  if (/^-?\d+(\.\d+)?$/.test(trimmed)) return Number(trimmed);
  return trimmed;
}

function coerceListValue(raw: string): unknown[] {
  return raw
    .split(',')
    .map((entry) => entry.trim())
    .filter((entry) => entry !== '')
    .map(coerceAttributeValue);
}

export interface ConditionDraft {
  attr: string;
  op: RuleOperator;
  value: string;
}

export interface RuleDraft {
  name: string;
  conditions: ConditionDraft[];
  serve: boolean;
}

export function emptyCondition(): ConditionDraft {
  // Starts from a catalogue preset so the row is never a blank text field.
  return defaultCondition();
}

export function emptyRuleDraft(): RuleDraft {
  return { name: '', conditions: [emptyCondition()], serve: true };
}

export function formatConditionValue(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (Array.isArray(value)) return value.map((entry) => String(entry)).join(', ');
  return String(value);
}

/** Splits a list-operator value into its individual tokens. */
export function splitListTokens(value: string): string[] {
  return value
    .split(',')
    .map((entry) => entry.trim())
    .filter((entry) => entry !== '');
}

/** Joins tokens back into the canonical comma-separated storage form. */
export function joinListTokens(tokens: readonly string[]): string {
  return tokens.join(', ');
}

export function isListOperator(op: RuleOperator): boolean {
  return op === 'in' || op === 'not_in';
}

export function draftFromRule(rule: {
  name?: string;
  conditions: RuleCondition[];
  serve: boolean;
}): RuleDraft {
  return {
    name: rule.name ?? '',
    serve: rule.serve,
    conditions:
      rule.conditions.length > 0
        ? rule.conditions.map((condition) => ({
            attr: condition.attr,
            op: condition.op,
            value: formatConditionValue(condition.value),
          }))
        : [emptyCondition()],
  };
}

/**
 * Returns the validation error for a draft, or `null` when it can be saved.
 * Rules must always carry at least one condition: an empty condition list is
 * an unconditional match server-side, which is almost never intended.
 */
/**
 * The server caps a rule at 25 conditions (`RuleCreate.conditions`), so the
 * builder stops there rather than letting you build something that looks valid
 * and then fails on save.
 */
export const MAX_RULE_CONDITIONS = 25;

export function validateRuleDraft(draft: RuleDraft): string | null {
  if (draft.conditions.length === 0) return 'Add at least one condition.';
  if (draft.conditions.length > MAX_RULE_CONDITIONS) {
    return `A rule can hold at most ${MAX_RULE_CONDITIONS} conditions.`;
  }
  for (const condition of draft.conditions) {
    if (!condition.attr.trim()) return 'Every condition needs an attribute.';
    if (operatorNeedsValue(condition.op) && !condition.value.trim()) {
      return `Provide a value for "${condition.attr.trim()}".`;
    }
  }
  return null;
}

export function toRuleConditions(draft: RuleDraft): RuleCondition[] {
  return draft.conditions.map((condition) => {
    const attr = condition.attr.trim();
    if (!operatorNeedsValue(condition.op)) {
      return { attr, op: condition.op };
    }
    const value =
      condition.op === 'in' || condition.op === 'not_in'
        ? coerceListValue(condition.value)
        : coerceAttributeValue(condition.value);
    return { attr, op: condition.op, value };
  });
}

/**
 * Parses the playground's attribute input. Accepts a JSON object or one
 * `key=value` pair per line, and coerces values the same way rule conditions
 * are coerced so both sides of a comparison agree on types.
 */
export function parseAttributeInput(raw: string): Record<string, unknown> {
  const trimmed = raw.trim();
  if (!trimmed) return {};

  if (trimmed.startsWith('{')) {
    try {
      const parsed: unknown = JSON.parse(trimmed);
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        return parsed as Record<string, unknown>;
      }
    } catch {
      // Fall through to line parsing so a partially typed object still works.
    }
  }

  const attributes: Record<string, unknown> = {};
  for (const line of trimmed.split('\n')) {
    const entry = line.trim();
    if (!entry) continue;
    const separator = entry.search(/[=:]/);
    if (separator < 1) continue;
    const key = entry.slice(0, separator).trim();
    if (!key) continue;
    attributes[key] = coerceAttributeValue(entry.slice(separator + 1));
  }
  return attributes;
}

export function formatAttributeInput(attributes: Record<string, unknown> | undefined): string {
  if (!attributes) return '';
  return Object.entries(attributes)
    .map(([key, value]) => `${key}=${formatConditionValue(value)}`)
    .join('\n');
}
