import { Link } from 'react-router-dom';

import { CodeBlock } from '../components/CodeBlock';

interface Section {
  id: string;
  label: string;
}

const SECTIONS: Section[] = [
  { id: 'quickstart', label: 'Quick start' },
  { id: 'install', label: 'Install' },
  { id: 'configuration', label: 'Configuration' },
  { id: 'how-it-works', label: 'How it works' },
  { id: 'precedence', label: 'Evaluation precedence' },
  { id: 'operators', label: 'Operators' },
  { id: 'api', label: 'API reference' },
  { id: 'attributes', label: 'Targeting attributes' },
  { id: 'refreshing', label: 'Refreshing & rollout' },
  { id: 'offline', label: 'Offline & disk cache' },
  { id: 'errors', label: 'Error handling' },
  { id: 'demo', label: 'Demo application' },
];

const QUICKSTART = `from catalyst_sdk import CatalystClient

client = CatalystClient(
    sdk_key="cp_prod_a1b2c3d4e5f6g7h8i9j0k1",
    project_id="7c9e6679-7425-40de-944b-e07fc1f90ae7",
    host="http://localhost:8000",
    env="prod",
)

if client.is_enabled("new-checkout", user_id="user_123",
                     attributes={"email": "alice@acme.com"}):
    render_express_checkout()
else:
    render_coming_soon()`;

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
    host=os.environ.get("CATALYST_HOST", "http://localhost:8000"),
    env="prod",
)
client.start_auto_refresh(interval=30)

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

const REFRESH = `client.start_auto_refresh(
    interval=30,
    on_error=lambda exc: logger.warning("catalyst refresh failed: %s", exc),
)

# Any failure keeps the last good snapshot serving, so a momentary
# network blip never changes what your users get.
...
client.stop_auto_refresh()`;

const MANUAL = `changed = client.refresh()   # True = new snapshot applied
                                  # False = server replied 304 Not Modified

client.version      # environment cache version currently loaded
client.is_ready     # bool, a snapshot is loaded
client.flag_keys()  # ['new-checkout', 'ai-assistant']
client.stats        # refresh counters, etag, last error`;

const OFFLINE = `from catalyst_sdk import CatalystClient

# Warm start with no network at all, from the on-disk snapshot.
client = CatalystClient(
    sdk_key=..., project_id=..., host=...,
    offline=True,
)

# Or let a normal construction fall back to cache if the API is down.
client = CatalystClient(sdk_key=..., project_id=..., host=...)`;

const CONTEXT = `ctx = request.headers.get("x-catalyst-context")  # JSON

result = client.evaluate("new-checkout", user_id="user_123")
if result.reason == "RULE_MATCH":
    log.info("rule %s served %s", result.rule_id, result.value)
else:
    log.info("no rule matched (%s)", result.reason)`;

const ERRORS = `from catalyst_sdk import CatalystClient, AuthorizationError, BootstrapError

client = CatalystClient(sdk_key=..., project_id=..., host=..., default_value=True)

try:
    client.refresh()
except AuthorizationError:
    # Key rejected or revoked. Will not fix itself -> handle loudly.
    alert_oncall()
except BootstrapError:
    # Network blip. The previous snapshot is still being served.
    logger.warning("refresh failed, serving stale snapshot")`;

const DEMO_ENV = `export CATALYST_SDK_KEY="cp_prod_..."
export CATALYST_PROJECT_ID="<project uuid>"
export CATALYST_HOST="http://localhost:8000"
export CATALYST_ENV="prod"

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
  ['host', 'no', 'Base URL of the Catalyst API. Defaults to http://localhost:8000.'],
  ['env', 'no', 'Which environment snapshot to load. Defaults to prod.'],
  ['timeout', 'no', 'Per-request HTTP timeout in seconds. Defaults to 5.0.'],
  ['default_value', 'no', 'Served for an unknown flag or before the first load. Defaults to False.'],
  ['offline', 'no', 'Skip the API entirely and load only from the disk cache.'],
  ['cache_path', 'no', 'None or True uses ~/.cache/catalyst, or pass a path. False disables it.'],
  ['raise_on_error', 'no', 'Re-raise refresh errors instead of keeping the last good snapshot.'],
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
            The <code>sdk-catalyst</code> package fetches your environment snapshot once, then
            answers every flag check in microseconds without touching the network. No polling in
            your request path, no latency budget spent on a round trip.
          </p>
          <div className="docs-hero-actions">
            <a className="btn-primary" href="#quickstart">Get started</a>
            <Link className="btn-gold-outline" to="/">Back to site</Link>
          </div>
          <ul className="docs-facts">
            <li><strong>&lt; 1 ms</strong><span>per evaluation</span></li>
            <li><strong>304</strong><span>unchanged refreshes</span></li>
            <li><strong>1</strong><span>runtime dependency</span></li>
          </ul>
        </div>
      </header>

      <div className="docs-layout">
        <nav className="docs-toc" aria-label="Documentation sections">
          <span className="docs-toc-title">On this page</span>
          {SECTIONS.map((section) => (
            <a key={section.id} href={`#${section.id}`}>{section.label}</a>
          ))}
        </nav>

        <main className="docs-content">
          <section id="quickstart" className="docs-section">
            <h2>Quick start</h2>
            <p>
              Fetch the snapshot at process startup, then check flags anywhere in your code. Every
              check after the first is a local lookup.
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
              The SDK never polls inside a request. It loads the snapshot once, and a background
              thread keeps it current.
            </p>
            <CodeBlock
              language="text"
              code={`  startup  ──▶  GET /api/v1/bootstrap          200 → replace snapshot
                         If-None-Match: <last etag>     304 → keep snapshot

                        background refresh thread
                              │
  is_enabled()  ──▶  in-memory snapshot  ──▶  no I/O`}
            />
            <ul className="docs-bullets">
              <li>
                <strong>Fetch on load.</strong> The snapshot is fetched in the constructor.
              </li>
              <li>
                <strong>Conditional refresh.</strong> Every refresh sends <code>If-None-Match</code>,
                so an unchanged environment costs a <code>304</code> with no body. The ETag derives
                from the environment version, which every snapshot-affecting mutation bumps.
              </li>
              <li>
                <strong>Atomic swap.</strong> A single assignment replaces the snapshot, so
                evaluation never sees a half-updated view.
              </li>
              <li>
                <strong>Degrades, never throws.</strong> A failed refresh keeps serving the last good
                snapshot.
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
            <p>The hot path. Never performs I/O.</p>
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

          <section id="refreshing" className="docs-section">
            <h2>Refreshing &amp; rollout</h2>
            <p>
              Start the background thread once at startup. It is a daemon, so it will not hold the
              process open on exit.
            </p>
            <CodeBlock code={REFRESH} />
            <p>You can also refresh on demand, and inspect what the client currently holds:</p>
            <CodeBlock code={MANUAL} />
            <p className="docs-note">
              There is no push channel. A toggle you flip in the dashboard is observed on the next
              refresh, not instantly.
            </p>
          </section>

          <section id="offline" className="docs-section">
            <h2>Offline &amp; disk cache</h2>
            <p>
              The last good snapshot is written to <code>~/.cache/catalyst</code> using an atomic
              write-then-rename, so a crash cannot leave a truncated file. Override the directory
              with <code>CATALYST_CACHE_DIR</code>.
            </p>
            <CodeBlock code={OFFLINE} />
          </section>

          <section id="errors" className="docs-section">
            <h2>Error handling</h2>
            <p>
              Evaluation never raises. An unknown flag, a missing snapshot, and a failed refresh all
              resolve to <code>default_value</code>, which fails safe to <code>False</code>.
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
