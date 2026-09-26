import type { RuleOperator } from '../api';

/**
 * How a value should be collected and compared for a given attribute.
 *
 * - `boolean`  -> True/False toggle, no typing
 * - `enum`     -> closed option list (single select or multi-select tokens)
 * - `number`   -> numeric stepper
 * - `version`  -> dotted numeric string compared numerically per segment
 * - `text`     -> free text
 * - `email`    -> email-ish text, usually used with `ends_with` for a domain
 */
export type AttributeKind = 'boolean' | 'enum' | 'number' | 'version' | 'text' | 'email';

export interface AttributeSpec {
  key: string;
  label: string;
  kind: AttributeKind;
  group: string;
  /** Closed option list for `enum` attributes. */
  options?: readonly string[];
  /** Operators offered first, in order, for this attribute. */
  operators: readonly RuleOperator[];
  /** Placeholder used when the attribute still needs free text. */
  placeholder?: string;
  /** A ready-made value used by the "use example" affordance. */
  example?: unknown;
  description: string;
}

const TEXT_OPS = [
  'equals',
  'not_equals',
  'contains',
  'starts_with',
  'ends_with',
  'in',
  'not_in',
  'exists',
  'not_exists',
] as const satisfies readonly RuleOperator[];

const NUMBER_OPS = [
  'equals',
  'not_equals',
  'greater_than',
  'greater_than_or_equal',
  'less_than',
  'less_than_or_equal',
  'in',
  'not_in',
  'exists',
  'not_exists',
] as const satisfies readonly RuleOperator[];

const VERSION_OPS = [
  'greater_than',
  'greater_than_or_equal',
  'less_than',
  'less_than_or_equal',
  'equals',
  'in',
  'exists',
  'not_exists',
] as const satisfies readonly RuleOperator[];

const BOOLEAN_OPS = ['equals', 'not_equals', 'exists', 'not_exists'] as const satisfies readonly RuleOperator[];

const ENUM_OPS = [
  'equals',
  'not_equals',
  'in',
  'not_in',
  'exists',
  'not_exists',
] as const satisfies readonly RuleOperator[];

const EMAIL_OPS = [
  'ends_with',
  'contains',
  'equals',
  'starts_with',
  'in',
  'not_in',
  'exists',
] as const satisfies readonly RuleOperator[];

/**
 * The attributes most feature flags are segmented on. Anything not listed here
 * still works through the "Custom attribute" escape hatch, so the catalogue is
 * a convenience rather than a limit.
 */
export const ATTRIBUTE_CATALOG: readonly AttributeSpec[] = [
  {
    key: 'email',
    label: 'Email address',
    kind: 'email',
    group: 'Identity',
    operators: EMAIL_OPS,
    placeholder: 'alice@acme.com',
    example: 'alice@acme.com',
    description: 'The user email address. Pair it with "ends with" to target a domain.',
  },
  {
    key: 'email_domain',
    label: 'Email domain',
    kind: 'text',
    group: 'Identity',
    operators: TEXT_OPS,
    placeholder: '@acme.com',
    example: '@acme.com',
    description: 'Just the domain part, e.g. @acme.com.',
  },
  {
    key: 'role',
    label: 'Role',
    kind: 'enum',
    group: 'Identity',
    options: ['admin', 'editor', 'viewer', 'owner', 'billing'],
    operators: ENUM_OPS,
    example: 'admin',
    description: 'The user role in your product.',
  },
  {
    key: 'user_id',
    label: 'User ID',
    kind: 'text',
    group: 'Identity',
    operators: TEXT_OPS,
    placeholder: 'user_123',
    example: 'user_123',
    description: 'The sticky rollout key. Targeting it directly overrides bucketing.',
  },
  {
    key: 'plan',
    label: 'Plan / tier',
    kind: 'enum',
    group: 'Billing',
    options: ['free', 'trial', 'starter', 'pro', 'enterprise'],
    operators: ENUM_OPS,
    example: 'pro',
    description: 'The subscription plan.',
  },
  {
    key: 'seats',
    label: 'Seats',
    kind: 'number',
    group: 'Billing',
    operators: NUMBER_OPS,
    example: 10,
    description: 'Number of paid seats on the account.',
  },
  {
    key: 'country',
    label: 'Country',
    kind: 'enum',
    group: 'Geography',
    options: ['IN', 'US', 'GB', 'DE', 'FR', 'JP', 'BR', 'AU', 'CA', 'SG'],
    operators: ENUM_OPS,
    example: 'IN',
    description: 'ISO country code from the request context.',
  },
  {
    key: 'region',
    label: 'Region',
    kind: 'enum',
    group: 'Geography',
    options: ['ap-south', 'us-east', 'us-west', 'eu-west', 'eu-central'],
    operators: ENUM_OPS,
    example: 'eu-west',
    description: 'Cloud region the request landed in.',
  },
  {
    key: 'app_version',
    label: 'App version',
    kind: 'version',
    group: 'Client',
    operators: VERSION_OPS,
    placeholder: '3.2.1',
    example: '3.2.1',
    description: 'Mobile or desktop client version. Compares segment by segment.',
  },
  {
    key: 'platform',
    label: 'Platform',
    kind: 'enum',
    group: 'Client',
    options: ['ios', 'android', 'web', 'desktop'],
    operators: ENUM_OPS,
    example: 'ios',
    description: 'The client platform.',
  },
  {
    key: 'is_beta',
    label: 'Beta cohort member',
    kind: 'boolean',
    group: 'Client',
    operators: BOOLEAN_OPS,
    example: true,
    description: 'Whether the user is in your beta program.',
  },
  {
    key: 'tenant_id',
    label: 'Tenant / account',
    kind: 'text',
    group: 'Account',
    operators: TEXT_OPS,
    placeholder: 'tenant_42',
    example: 'tenant_42',
    description: 'B2B account identifier.',
  },
  {
    key: 'device',
    label: 'Device',
    kind: 'enum',
    group: 'Client',
    options: ['desktop', 'tablet', 'mobile'],
    operators: ENUM_OPS,
    example: 'mobile',
    description: 'Device class reported by the client.',
  },
];

const BY_KEY = new Map(ATTRIBUTE_CATALOG.map((spec) => [spec.key, spec]));

/** Sentinel used by the attribute select to offer a free-text attribute. */
export const CUSTOM_ATTRIBUTE = '__custom__';

/** The condition a freshly added row starts from: a preset, never blank. */
export function defaultCondition(): { attr: string; op: RuleOperator; value: string } {
  const spec = ATTRIBUTE_CATALOG[0];
  const op = spec.operators[0];
  return { attr: spec.key, op, value: exampleValueFor(spec.key, op) };
}

export function findAttribute(key: string): AttributeSpec | undefined {
  return BY_KEY.get(key);
}

export function attributeLabel(key: string): string {
  if (key === 'user_id') return 'User ID';
  return findAttribute(key)?.label ?? key;
}

export function attributeKind(key: string): AttributeKind {
  return findAttribute(key)?.kind ?? 'text';
}

export function attributeOptions(key: string): readonly string[] {
  return findAttribute(key)?.options ?? [];
}

/** Operators worth offering for an attribute, best-fit first. */
export function operatorsForAttribute(key: string): readonly RuleOperator[] {
  return findAttribute(key)?.operators ?? TEXT_OPS;
}

export function attributeGroups(): { group: string; specs: AttributeSpec[] }[] {
  const groups = new Map<string, AttributeSpec[]>();
  for (const spec of ATTRIBUTE_CATALOG) {
    const existing = groups.get(spec.group);
    if (existing) existing.push(spec);
    else groups.set(spec.group, [spec]);
  }
  return [...groups.entries()].map(([group, specs]) => ({ group, specs }));
}

/** A representative value to seed the value control with. */
export function exampleValueFor(key: string, op: RuleOperator): string {
  const spec = findAttribute(key);
  if (!spec) return '';
  if (op === 'in' || op === 'not_in') {
    const options = spec.options ?? [];
    if (options.length >= 2) return `${options[0]}, ${options[1]}`;
    if (options.length === 1) return options[0];
    return spec.example === undefined ? '' : String(spec.example);
  }
  if (spec.example === undefined) return '';
  if (Array.isArray(spec.example)) return spec.example.join(', ');
  return String(spec.example);
}

/**
 * Version-aware comparison so `app_version >= 3.2` behaves the way a release
 * engineer expects instead of comparing strings character by character.
 */
function compareVersions(left: string, right: string): number {
  const a = String(left).split(/[.\-+]/);
  const b = String(right).split(/[.\-+]/);
  const length = Math.max(a.length, b.length);
  for (let i = 0; i < length; i++) {
    const x = Number.parseInt(a[i] ?? '0', 10);
    const y = Number.parseInt(b[i] ?? '0', 10);
    if (Number.isNaN(x) || Number.isNaN(y)) {
      const sx = a[i] ?? '';
      const sy = b[i] ?? '';
      if (sx !== sy) return sx < sy ? -1 : 1;
      continue;
    }
    if (x !== y) return x < y ? -1 : 1;
  }
  return 0;
}

/**
 * Client-side mirror of the backend evaluator's `match_condition`, used only
 * for the live match preview while a rule is being built. The server remains
 * the source of truth for what is actually served.
 */
export function previewConditionMatch(
  condition: { attr: string; op: RuleOperator; value?: unknown },
  attributes: Record<string, unknown>,
): boolean {
  const op = condition.op;
  const present = Object.prototype.hasOwnProperty.call(attributes, condition.attr);
  if (op === 'exists') return present;
  if (op === 'not_exists') return !present;
  if (!present) return false;

  const actual = attributes[condition.attr];
  const kind = attributeKind(condition.attr);
  const target = condition.value;

  const asList = (value: unknown): unknown[] =>
    Array.isArray(value) ? value : String(value ?? '').split(',').map((entry) => entry.trim()).filter(Boolean);

  const compare = (a: unknown, b: unknown): number => {
    if (kind === 'version') return compareVersions(String(a), String(b));
    const na = Number(a);
    const nb = Number(b);
    if (!Number.isNaN(na) && !Number.isNaN(nb)) return na === nb ? 0 : na < nb ? -1 : 1;
    return String(a) === String(b) ? 0 : String(a) < String(b) ? -1 : 1;
  };

  switch (op) {
    case 'equals':
      return actual === target || String(actual) === String(target);
    case 'not_equals':
      return !(actual === target || String(actual) === String(target));
    case 'in':
      return asList(target).some((entry) => actual === entry || String(actual) === String(entry));
    case 'not_in':
      return !asList(target).some((entry) => actual === entry || String(actual) === String(entry));
    case 'contains':
      return String(target).toLowerCase().includes(String(actual).toLowerCase());
    case 'starts_with':
      return String(actual).toLowerCase().startsWith(String(target).toLowerCase());
    case 'ends_with':
      return String(actual).toLowerCase().endsWith(String(target).toLowerCase());
    case 'greater_than':
      return compare(actual, target) > 0;
    case 'greater_than_or_equal':
      return compare(actual, target) >= 0;
    case 'less_than':
      return compare(actual, target) < 0;
    case 'less_than_or_equal':
      return compare(actual, target) <= 0;
    default:
      return false;
  }
}

/** True when every condition in a rule matches the given context. */
export function previewRuleMatch(
  conditions: readonly { attr: string; op: RuleOperator; value?: unknown }[],
  attributes: Record<string, unknown>,
): boolean {
  return conditions.every((condition) => previewConditionMatch(condition, attributes));
}
