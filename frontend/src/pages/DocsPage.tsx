import { useMemo, useState } from 'react';
import type { FormEvent } from 'react';
import { Link } from 'react-router-dom';

import { CodeBlock } from '../components/CodeBlock';
import { searchSections } from '../lib/docsSearch';
import type { DocsSection } from '../lib/docsSearch';

const SECTIONS: DocsSection[] = [
  {
    id: 'quickstart',
    label: 'Quick start',
    summary: 'Construct a client and check a flag.',
    keywords: ['start', 'setup', 'example', 'first check'],
  },
  {
    id: 'install',
    label: 'Install',
    summary: 'pip install sdk-catalyst, Python 3.11 or newer.',
    keywords: ['pip', 'package', 'pypi', 'dependency', 'setup'],
  },
  {
    id: 'host',
    label: 'Choosing the API host',
    summary: 'The hosted API is the default; override it per client or per process.',
    keywords: ['host', 'base url', 'catalyst_host', 'self hosted', 'staging', 'local', 'onrender', 'override'],
  },
  {
    id: 'configuration',
    label: 'Configuration',
    summary: 'Every constructor argument and what it does.',
    keywords: ['options', 'arguments', 'kwargs', 'timeout', 'default_value', 'settings', 'config'],
  },
  {
    id: 'how-it-works',
    label: 'How it works',
    summary: 'A conditional read per check, then a local decision.',
    keywords: ['etag', '304', 'if-none-match', 'snapshot', 'request', 'latency', 'architecture'],
  },
  {
    id: 'caching',
    label: 'Server-side caching',
    summary: 'The API serves snapshots from Redis, keyed by environment version.',
    keywords: ['redis', 'cache', 'invalidation', 'ttl', 'performance', 'postgres', 'database'],
  },
  {
    id: 'precedence',
    label: 'Evaluation precedence',
    summary: 'Kill switch, then rules, then rollout, then the default.',
    keywords: ['order', 'kill switch', 'rollout', 'percentage', 'murmur', 'bucket', 'sticky'],
  },
  {
    id: 'operators',
    label: 'Operators',
    summary: 'The condition vocabulary available to targeting rules.',
    keywords: ['equals', 'in', 'contains', 'greater_than', 'exists', 'comparison', 'conditions'],
  },
  {
    id: 'api',
    label: 'API reference',
    summary: 'is_enabled, evaluate, get_all, and route wrappers.',
    keywords: ['is_enabled', 'evaluate', 'get_all', 'decorator', 'flask', 'fastapi', 'method'],
  },
  {
    id: 'attributes',
    label: 'Targeting attributes',
    summary: 'Context attributes matched against rules, and common presets.',
    keywords: ['context', 'email', 'plan', 'role', 'country', 'segment', 'properties'],
  },
  {
    id: 'freshness',
    label: 'Freshness',
    summary: 'When a check sees a change, and how to take refreshes into your hands.',
    keywords: ['refresh', 'auto refresh', 'stale', 'propagation', 'interval', 'read', 'update'],
  },
  {
    id: 'offline',
    label: 'Offline & disk cache',
    summary: 'The last good snapshot on disk, for cold starts and air-gapped runs.',
    keywords: ['cache_path', 'catalyst_cache_dir', 'offline', 'disk', 'fallback', 'cold start'],
  },
  {
    id: 'errors',
    label: 'Error handling',
    summary: 'What raises, what degrades, and every evaluation reason.',
    keywords: ['exception', 'authorizationerror', 'bootstraperror', 'reason', 'fail safe', 'timeout'],
  },
  {
    id: 'demo',
    label: 'Demo application',
    summary: 'A runnable FastAPI service that gates endpoints and explains decisions.',
    keywords: ['example app', 'fastapi demo', 'curl', 'health', 'run'],
  },
];

const QUICKSTART = `from catalyst_sdk import CatalystClient

# No host needed: the client talks to the hosted Catalyst API.
client = CatalystClient(
    sdk_key="cp_prod_a1b2c3d4e5f6g7h8i9j0k1",
    project_id="7c9e6679-7425-40de-944b-e07fc1f90ae7",
    env="prod",
)

if client.is_enabled("new-checkout", user_id="user_123",
                     attributes={"email": "alice@acme.com"}):
    render_express_checkout()
else:
    render_coming_soon()`;

const HOSTS = `# Point one client somewhere else (staging, self-hosted, a tunnel).
client = CatalystClient(
    sdk_key=..., project_id=...,
    host="https://catalyst-api-uakz.onrender.com",
)

# Or set the default for a whole process.
export CATALYST_HOST="http://localhost:8000"`;

const INSTALL = `pip install sdk-catalyst

# From a checkout
uv sync
# or
pip install -e ".[dev]"`;

const FLASK = `from flask import Flask, jsonify, request
from catalyst_sdk import CatalystClient

app = Flask(__name__)
client = CatalystClient(
    sdk_key=os.environ["CATALYST_SDK_KEY"],
    project_id=os.environ["CATALYST_PROJECT_ID"],
    host=os.environ.get("CATALYST_HOST"),  # unset -> hosted API
    env="prod",
)

@app.get("/checkout")
def checkout():
    email = request.headers.get("x-user-email")
    enabled = client.is_enabled(
        "new-checkout",
        user_id=request.args.get("user_id", "anonymous"),
        attributes={"email": email} if email else None,
    )
    return jsonify({"express_checkout": enabled})`;

const DECORATOR = `from functools import wraps
from catalyst_sdk import CatalystClient

client = CatalystClient(**settings)

def gated(flag_key):
    """Skip a handler unless the flag is on for this caller."""
    def decorator(view):
        @wraps(view)
        def wrapper(*args, **kwargs):
            user = current_user()
            if not client.is_enabled(
                flag_key,
                user_id=user.id,
                attributes={"plan": user.plan, "country": user.country},
            ):
                return jsonify({"error": "feature not available"}), 403
            return view(*args, **kwargs)
        return wrapper
    return decorator

@gated("ai-assistant")
def ask_ai(): ...`;

const INSPECT = `result = client.evaluate("new-checkout",
                           user_id="user_123",
                           attributes={"email": "alice@acme.com"})

result.value          # True
result.reason         # 'RULE_MATCH'
result.rule_id        # the targeting rule that fired
result.flag_version   # snapshot version the decision came from`;

const BULK = `# Evaluate the whole snapshot in one pass, e.g. to render a UI.
flags = client.get_all(user_id="user_123", attributes={"plan": "pro"})
# {"new-checkout": True, "ai-assistant": False}`;

const READ_MODEL = `# The default: every check reads, then decides locally.
client = CatalystClient(sdk_key=..., project_id=...)

# Opt out and evaluate from memory only. Freshness is then yours to drive.
client = CatalystClient(sdk_key=..., project_id=..., refresh_on_evaluate=False)

# A dead API should not add its timeout to every check.
client = CatalystClient(sdk_key=..., project_id=..., failure_backoff=15.0)`;

const REFRESH = `client.start_auto_refresh(
    interval=30,
    on_error=lambda exc: logger.warning("catalyst refresh failed: %s", exc),
)

# Only useful with refresh_on_evaluate=False; otherwise the background
# thread is redundant with the per-check read.
...
client.stop_auto_refresh()`;

const MANUAL = `changed = client.refresh()   # True = new snapshot applied
                                  # False = server replied 304 Not Modified

client.version      # environment version currently loaded
client.is_ready     # bool, a snapshot is loaded
client.flag_keys()  # ['new-checkout', 'ai-assistant']
client.stats        # refresh counters, etag, host, last error`;

const OFFLINE = `from catalyst_sdk import CatalystClient

# Warm start with no network at all, from the on-disk snapshot.
client = CatalystClient(
    sdk_key=..., project_id=...,
    offline=True,
)

# A failed read also falls back to the cache, then to default_value.`;

const CONTEXT = `ctx = request.headers.get("x-catalyst-context")  # JSON

result = client.evaluate("new-checkout", user_id="user_123")
if result.reason == "RULE_MATCH":
    log.info("rule %s served %s", result.rule_id, result.value)
else:
    log.info("no rule matched (%s)", result.reason)`;

const ERRORS = `from catalyst_sdk import CatalystClient, AuthorizationError, BootstrapError

client = CatalystClient(sdk_key=..., project_id=..., default_value=True)

try:
    client.refresh()
except AuthorizationError:
    # Key rejected or revoked. Will not fix itself -> handle loudly.
    alert_oncall()
except BootstrapError:
    # Network blip. The previous snapshot is still being served.
    logger.warning("refresh failed, serving stale snapshot")

# Checks never raise. Set raise_on_error=True to find out instead.
client.is_enabled("new-checkout", user_id="user_123")  # -> False on failure`;

const DEMO_ENV = `export CATALYST_SDK_KEY="cp_prod_..."
export CATALYST_PROJECT_ID="<project uuid>"
export CATALYST_ENV="prod"

# Only needed when running against your own API.
# export CATALYST_HOST="http://localhost:8000"

python examples/fastapi_demo/app.py`;

const DEMO_CALLS = `# A flag-gated endpoint
curl localhost:9000/api/checkout?user_id=user_123 \\
  -H 'x-user-email: alice@acme.com'

# Explain a single decision
curl "localhost:9000/api/inspect?flag=new-checkout&user_id=user_123"

# Every flag at once
curl "localhost:9000/api/flags?user_id=user_123"

# Snapshot freshness, separating "API down" from "stale but serving"
curl localhost:9000/health`;

const CONFIG_ROWS: [string, string, string][] = [
  ['sdk_key', 'yes', 'An SDK key from the API Keys tab, sent as X-SDK-Key.'],
  ['project_id', 'yes', 'The bootstrap endpoint is strictly project scoped, so the SDK cannot infer it from the key.'],
  ['host', 'no', 'Base URL of the Catalyst API. Omit it for the hosted API, or set CATALYST_HOST.'],
  ['env', 'no', 'Which environment snapshot to load. Defaults to prod.'],
  ['timeout', 'no', 'Per-request HTTP timeout in seconds. Defaults to 5.0.'],
  ['default_value', 'no', 'Served for an unknown flag or when no snapshot can be loaded. Defaults to False.'],
  ['refresh_on_evaluate', 'no', 'Read the snapshot as part of each check. Defaults to True.'],
  ['failure_backoff', 'no', 'Seconds to stop retrying after a failed read. Defaults to 5.0.'],
  ['offline', 'no', 'Skip the API entirely and load only from the disk cache. Implies refresh_on_evaluate=False.'],
  ['cache_path', 'no', 'None or True uses ~/.cache/catalyst, or pass a path. False disables it.'],
  ['raise_on_error', 'no', 'Let read failures raise out of evaluation instead of degrading.'],
];

const REASONS: [string, string][] = [
  ['KILL_SWITCH_ACTIVE', 'The emergency kill switch is engaged, so the flag default is served.'],
  ['RULE_MATCH', 'A targeting rule matched. Inspect rule_id for which one.'],
  ['PERCENTAGE_ROLLOUT', 'No rule matched, but the user fell inside the sticky rollout bucket.'],
  ['DEFAULT_VALUE', 'Nothing matched. The flag default is served.'],
  ['FLAG_NOT_FOUND', 'The key is not in the snapshot. Serves default_value.'],
  ['NO_SNAPSHOT', 'No snapshot has loaded yet. Serves default_value.'],
];

const OPERATORS: [string, string, string][] = [
  ['equals', 'is exactly', 'Case-sensitive. A boolean attribute only equals the real boolean.'],
  ['not_equals', 'is not', 'Case-sensitive.'],
  ['in', 'is one of', 'Accepts a list, or a comma-separated string.'],
  ['not_in', 'is not one of', 'Accepts a list, or a comma-separated string.'],
  ['contains', 'contains', 'Case-insensitive substring.'],
  ['starts_with', 'starts with', 'Case-insensitive prefix.'],
  ['ends_with', 'ends with', 'Case-insensitive suffix.'],
  ['greater_than', '>', 'Numeric comparison.'],
  ['greater_than_or_equal', '>=', 'Numeric comparison.'],
  ['less_than', '<', 'Numeric comparison.'],
  ['less_than_or_equal', '<=', 'Numeric comparison.'],
  ['exists', 'is present', 'Attribute exists. The value is ignored.'],
  ['not_exists', 'is missing', 'Attribute is absent. The value is ignored.'],
];

const ATTRIBUTES: [string, string][] = [
  ['email', 'alice@acme.com'],
  ['email_domain', '@acme.com'],
  ['role', 'admin'],
  ['plan', 'pro'],
  ['seats', '10'],
  ['country', 'IN'],
  ['region', 'eu-west'],
  ['app_version', '3.2.1'],
  ['platform', 'ios'],
  ['is_beta', 'true'],
  ['tenant_id', 'tenant_42'],
  ['user_id', 'user_123'],
];

export function DocsPage() {
  const [query, setQuery] = useState('');
  const [activeId, setActiveId] = useState<string | null>(null);
  const results = useMemo(() => searchSections(SECTIONS, query), [query]);
  const searching = query.trim().length > 0;

  const goTo = (id: string) => {
    setActiveId(id);
    document.getElementById(id)?.scrollIntoView({ behavior: 'smooth', block: 'start' });
  };

  const handleSearch = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (results.length > 0) goTo(results[0].id);
  };

  return (
    <div className="docs-page">
      <header className="docs-hero">
        <div className="docs-hero-inner">
          <span className="brand-logo docs-logo">C</span>
          <span className="eyebrow">Catalyst SDK</span>
          <h1>
            Feature flags, evaluated <em>locally.</em>
          </h1>
          <p className="docs-lede">
            The <code>sdk-catalyst</code> package reads your environment snapshot as it evaluates
            and decides locally. Each check is a conditional request, so an unchanged environment
            costs a <code>304</code> with no body, and a dashboard toggle is picked up on the very
            next check.
          </p>
          <div className="docs-hero-actions">
            <a className="btn-primary" href="#quickstart">Get started</a>
            <Link className="btn-gold-outline" to="/">Back to site</Link>
          </div>
          <ul className="docs-facts">
            <li><strong>&lt; 1 ms</strong><span>local decision</span></li>
            <li><strong>304</strong><span>unchanged checks</span></li>
            <li><strong>1</strong><span>runtime dependency</span></li>
          </ul>
        </div>
      </header>

      <div className="docs-layout">
        <nav className="docs-toc" aria-label="Documentation sections">
          <form className="docs-search" role="search" onSubmit={handleSearch}>
            <label className="docs-toc-title" htmlFor="docs-search-input">Search the docs</label>
            <div className="docs-search-row">
              <input
                id="docs-search-input"
                type="search"
                value={query}
                placeholder="e.g. redis, etag, host"
                autoComplete="off"
                onChange={(event) => setQuery(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === 'Escape') setQuery('');
                }}
              />
              <button type="submit" className="docs-search-button">Go</button>
            </div>
            {searching && (
              <p className="docs-search-status" role="status">
                {results.length === 0
                  ? 'No matching sections'
                  : `${results.length} matching section${results.length === 1 ? '' : 's'}`}
              </p>
            )}
          </form>

          <span className="docs-toc-title">{searching ? 'Results' : 'On this page'}</span>
          {(searching ? results : SECTIONS).map((section) => (
            <a
              key={section.id}
              href={`#${section.id}`}
              className={activeId === section.id ? 'docs-toc-active' : undefined}
              aria-current={activeId === section.id ? 'true' : undefined}
              onClick={() => setActiveId(section.id)}
            >
              {section.label}
            </a>
          ))}
        </nav>

        <main className="docs-content">
          <section id="quickstart" className="docs-section">
            <h2>Quick start</h2>
            <p>
              Construct the client once, then check flags anywhere in your code. Construction does
              no I/O; the first check is what reads the snapshot.
            </p>
            <CodeBlock code={QUICKSTART} />
            <p className="docs-note">
              You need two values from the dashboard: an <strong>SDK key</strong> from the project's
              API Keys tab, and the <strong>project id</strong>. Both are shown on the API Keys page.
            </p>
          </section>

          <section id="install" className="docs-section">
            <h2>Install</h2>
            <CodeBlock code={INSTALL} language="bash" />
            <p className="docs-note">
              The distribution is named <strong>sdk-catalyst</strong> — the{' '}
              <code>catalyst-sdk</code> name is taken on PyPI by an unrelated project. The import
              name is unchanged, so code keeps using <code>from catalyst_sdk import CatalystClient</code>.
              Requires Python 3.11 or newer.
            </p>
          </section>

          <section id="host" className="docs-section">
            <h2>Choosing the API host</h2>
            <p>
              The client calls the hosted Catalyst API by default, so a working setup needs nothing
              but a key and a project id. Pass <code>host</code> to send it somewhere else, or set{' '}
              <code>CATALYST_HOST</code> to move a whole process.
            </p>
            <CodeBlock code={HOSTS} />
            <ul className="docs-bullets">
              <li>
                <strong>Precedence.</strong> The <code>host</code> argument wins over{' '}
                <code>CATALYST_HOST</code>, which wins over the hosted default.
              </li>
              <li>
                <strong>Worth overriding for</strong> a staging deployment, a self-hosted instance,
                or a tunnel to your laptop during development.
              </li>
              <li>
                <strong>Not a secret.</strong> The key travels in a header, so host configuration can
                live in your deployment config alongside it.
              </li>
            </ul>
          </section>

          <section id="configuration" className="docs-section">
            <h2>Configuration</h2>
            <div className="docs-table-wrap">
              <table className="docs-table">
                <thead>
                  <tr><th>Argument</th><th>Required</th><th>Notes</th></tr>
                </thead>
                <tbody>
                  {CONFIG_ROWS.map(([name, required, notes]) => (
                    <tr key={name}>
                      <td><code>{name}</code></td>
                      <td className={required === 'yes' ? 'docs-required' : ''}>{required}</td>
                      <td>{notes}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section id="how-it-works" className="docs-section">
            <h2>How it works</h2>
            <p>
              Nothing is fetched at import or construction time. A check reads the snapshot with a
              conditional request, then makes the decision locally against it.
            </p>
            <CodeBlock
              language="text"
              code={`  is_enabled("new-checkout", user_id="u1")
        │
        ├──▶  GET /api/v1/bootstrap
        │      If-None-Match: <last etag>
        │        304            → snapshot unchanged, no body
        │        200            → replace snapshot
        │
        └──▶  local decision against the snapshot  →  bool`}
            />
            <ul className="docs-bullets">
              <li>
                <strong>Conditional read.</strong> Every check sends <code>If-None-Match</code>, so
                an unchanged environment costs a <code>304</code> with no body. The ETag derives from
                the environment version, which every snapshot-affecting mutation bumps.
              </li>
              <li>
                <strong>Atomic swap.</strong> A single assignment replaces the snapshot, so
                evaluation never sees a half-updated view.
              </li>
              <li>
                <strong>One request per burst.</strong> Concurrent checks collapse into a single
                read, so a thread pool or a busy event loop does not stampede the API.
              </li>
              <li>
                <strong>Degrades, never throws.</strong> A failed read keeps serving the last good
                snapshot, then the disk cache, then <code>default_value</code>.
              </li>
            </ul>
            <p className="docs-note">
              Prefer to keep reads out of the request path entirely? Set{' '}
              <code>refresh_on_evaluate=False</code> and drive freshness yourself. See{' '}
              <a href="#freshness">Freshness</a>.
            </p>
          </section>

          <section id="caching" className="docs-section">
            <h2>Server-side caching</h2>
            <p>
              The read your client makes is cheap, because the API answers it from Redis rather than
              from PostgreSQL. A project environment's snapshot is cached under its own key and
              validated against the environment version on every request.
            </p>
            <ul className="docs-bullets">
              <li>
                <strong>Version-driven invalidation.</strong> Every mutation that changes a flag,
                its state, or its rules bumps the environment version, which both moves the ETag and
                evicts the cached snapshot. A stale entry cannot be served.
              </li>
              <li>
                <strong>304 short-circuits earlier still.</strong> When your ETag already matches, the
                snapshot is never loaded at all.
              </li>
              <li>
                <strong>Shared by both endpoints.</strong> <code>/evaluate</code> and{' '}
                <code>/batch-evaluate</code> read the same cached snapshot, so server-side
                evaluation is a local decision too.
              </li>
              <li>
                <strong>Nothing to install.</strong> If Redis is unreachable the API rebuilds from
                PostgreSQL and keeps serving. A cache outage is a slowdown, not an outage.
              </li>
            </ul>
          </section>

          <section id="precedence" className="docs-section">
            <h2>Evaluation precedence</h2>
            <p>The SDK mirrors the server exactly, in this order:</p>
            <ol className="docs-steps">
              <li><strong>Emergency kill switch</strong> &rarr; serve the flag default</li>
              <li><strong>Targeting rules</strong>, ascending <code>priority</code>, first match wins &rarr; serve its value</li>
              <li><strong>Percentage rollout</strong> &rarr; deterministic Murmur3 bucket over <code>flag_key:user_id</code></li>
              <li><strong>Flag default</strong></li>
            </ol>
            <p>
              Bucketing is pure MurmurHash3, vendored rather than pulled from a native extension, and
              verified against the server on every release. The same user always lands in the same
              bucket, in every SDK and on the server.
            </p>
          </section>

          <section id="operators" className="docs-section">
            <h2>Operators</h2>
            <p>
              All conditions in a rule are ANDed. A missing context attribute makes a condition
              false, so the rule safely skips instead of raising.
            </p>
            <div className="docs-table-wrap">
              <table className="docs-table">
                <thead>
                  <tr><th>Operator</th><th>Reads as</th><th>Semantics</th></tr>
                </thead>
                <tbody>
                  {OPERATORS.map(([op, reads, semantics]) => (
                    <tr key={op}>
                      <td><code>{op}</code></td>
                      <td>{reads}</td>
                      <td>{semantics}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="docs-note">
              Short aliases (<code>eq</code>, <code>neq</code>, <code>gt</code>, <code>gte</code>,{' '}
              <code>lt</code>, <code>lte</code>, <code>notExists</code>) are accepted and normalized.
            </p>
          </section>

          <section id="api" className="docs-section">
            <h2>API reference</h2>

            <h3>is_enabled</h3>
            <p>The hot path: one conditional read, then a local decision.</p>
            <CodeBlock code={`client.is_enabled(
    flag_key: str,
    user_id: str = "",
    attributes: dict | None = None,
    default_value: bool | None = None,
) -> bool`} />

            <h3>evaluate</h3>
            <p>Same evaluation, but returns the full decision so you can explain it.</p>
            <CodeBlock code={INSPECT} />

            <h3>get_all</h3>
            <CodeBlock code={BULK} />

            <h3>Wrapping a route</h3>
            <CodeBlock code={DECORATOR} caption="A decorator that gates a handler on a flag." />

            <h3>Flask</h3>
            <CodeBlock code={FLASK} />
          </section>

          <section id="attributes" className="docs-section">
            <h2>Targeting attributes</h2>
            <p>
              Attributes are whatever your targeting rules reference. Pass them per call; they are
              never sent to the API, only compared locally. The dashboard's rule builder suggests
              these common ones:
            </p>
            <div className="docs-attr-grid">
              {ATTRIBUTES.map(([key, example]) => (
                <div key={key} className="docs-attr">
                  <code>{key}</code>
                  <span>{example}</span>
                </div>
              ))}
            </div>
            <CodeBlock
              code={CONTEXT}
              caption="Inspect result.reason and result.rule_id to understand a decision."
            />
          </section>

          <section id="freshness" className="docs-section">
            <h2>Freshness</h2>
            <p>
              By default every check reads, so a toggle you flip in the dashboard is observed on the
              next check &mdash; there is no propagation delay to tune.
            </p>
            <CodeBlock code={READ_MODEL} />
            <h3>Taking over the schedule</h3>
            <p>
              With <code>refresh_on_evaluate=False</code> the client becomes purely in-memory, and a
              daemon thread is the way to keep it current. It will not hold the process open on exit.
            </p>
            <CodeBlock code={REFRESH} />
            <p>You can also refresh on demand, and inspect what the client currently holds:</p>
            <CodeBlock code={MANUAL} />
            <p className="docs-note">
              A failed read is retried no more than once per <code>failure_backoff</code> window, so
              an unreachable API costs one timeout per window instead of one per request.
            </p>
          </section>

          <section id="offline" className="docs-section">
            <h2>Offline &amp; disk cache</h2>
            <p>
              The last good snapshot is written to <code>~/.cache/catalyst</code> using an atomic
              write-then-rename, so a crash cannot leave a truncated file. Override the directory
              with <code>CATALYST_CACHE_DIR</code>. A first read that fails falls back here before
              giving up on <code>default_value</code>.
            </p>
            <CodeBlock code={OFFLINE} />
          </section>

          <section id="errors" className="docs-section">
            <h2>Error handling</h2>
            <p>
              Evaluation never raises. An unknown flag, a missing snapshot, and a failed read all
              resolve to <code>default_value</code>, which fails safe to <code>False</code> &mdash;
              a flag check inside someone else's request must not become a 500.
            </p>
            <CodeBlock code={ERRORS} />
            <div className="docs-table-wrap">
              <table className="docs-table">
                <thead>
                  <tr><th>Exception</th><th>When</th><th>Behaviour</th></tr>
                </thead>
                <tbody>
                  <tr>
                    <td><code>ConfigurationError</code></td>
                    <td>Missing <code>sdk_key</code>, <code>project_id</code>, or <code>host</code></td>
                    <td>Raised at construction</td>
                  </tr>
                  <tr>
                    <td><code>AuthorizationError</code></td>
                    <td>Key rejected or revoked</td>
                    <td>Always propagates. A bad key will not fix itself.</td>
                  </tr>
                  <tr>
                    <td><code>BootstrapError</code></td>
                    <td>Network or protocol failure</td>
                    <td>Logged; the previous snapshot keeps serving. Set <code>raise_on_error</code> to propagate.</td>
                  </tr>
                  <tr>
                    <td>read failure during <code>is_enabled</code></td>
                    <td>API unreachable, key revoked, or <code>raise_on_error</code> set</td>
                    <td>Absorbed by default: last good snapshot, then the disk cache, then the default. Set <code>raise_on_error</code> to see it.</td>
                  </tr>
                </tbody>
              </table>
            </div>
            <h3>Evaluation reasons</h3>
            <div className="docs-table-wrap">
              <table className="docs-table">
                <thead>
                  <tr><th><code>result.reason</code></th><th>Meaning</th></tr>
                </thead>
                <tbody>
                  {REASONS.map(([reason, meaning]) => (
                    <tr key={reason}><td><code>{reason}</code></td><td>{meaning}</td></tr>
                  ))}
                </tbody>
              </table>
            </div>
          </section>

          <section id="demo" className="docs-section">
            <h2>Demo application</h2>
            <p>
              A runnable FastAPI service lives in the package at{' '}
              <code>examples/fastapi_demo/app.py</code>. It gates a checkout endpoint, explains its
              decisions, and exposes a health endpoint that separates &ldquo;API down&rdquo; from
              &ldquo;stale but serving&rdquo;.
            </p>
            <CodeBlock code={DEMO_ENV} language="bash" />
            <CodeBlock code={DEMO_CALLS} language="bash" />
          </section>

          <footer className="docs-footer">
            <p>
              Ready to try it? Create a project in the dashboard, mint an SDK key from the{' '}
              <strong>API Keys</strong> tab, and paste both values into your client.
            </p>
            <div className="docs-hero-actions">
              <Link className="btn-primary" to="/register">Create an account <span aria-hidden="true">→</span></Link>
              <Link className="btn-gold-outline" to="/login">Sign in</Link>
            </div>
          </footer>
        </main>
      </div>
    </div>
  );
}
