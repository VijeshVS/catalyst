import { Link } from 'react-router-dom';

const FEATURES = [
  {
    icon: '✦',
    title: 'Feature Flags',
    description: 'Give every team a shared language for turning ideas on, safely and incrementally.',
  },
  {
    icon: '!',
    title: 'Emergency Kill Switch',
    description: 'Put a calm, immediate stop between a bad release and your users.',
  },
  {
    icon: '↗',
    title: 'Percentage Rollout',
    description: 'Ship to 1% or 100% with deterministic, sticky audience bucketing.',
  },
  {
    icon: '◈',
    title: 'SDK-Ready Bootstrap',
    description: 'One versioned snapshot powers fast, low-latency evaluation everywhere.',
  },
];

const PROBLEMS = [
  {
    title: 'Immediate user exposure',
    description:
      'A feature reaches 100% of users the moment the deployment finishes, so a single bug or unexpected behaviour lands with full blast radius.',
  },
  {
    title: 'Deployment-dependent rollbacks',
    description:
      'Disabling a faulty feature needs another code change, another build, another deploy — minutes or hours instead of one toggle.',
  },
  {
    title: 'No gradual rollout',
    description:
      'There is no 1% → 25% → 100% ramp, and no way to hand a feature to beta testers or one named account before everyone else.',
  },
  {
    title: 'No emergency kill switch',
    description:
      'On-call engineers cannot switch a problem feature off during a live incident without triggering another deployment.',
  },
];

const OBJECTIVES = [
  {
    title: 'Decouple deploy from release',
    description: 'Dark-launch code safely at 0% rollout, then turn it on without touching the build.',
    trace: 'percentage = 0',
  },
  {
    title: 'Instant kill switch',
    description: 'One toggle returns false to everyone, with no deploy in the path.',
    trace: 'KILL_SWITCH_ACTIVE',
  },
  {
    title: 'Deterministic sticky rollouts',
    description: '0–100% bucketing that never reshuffles a user between checks.',
    trace: 'Murmur3 · flag:user',
  },
  {
    title: 'Attribute-based targeting',
    description: 'First-match-wins rules over 13 operators, ANDed inside a rule.',
    trace: 'TargetingRule · 13 ops',
  },
  {
    title: 'Sub-millisecond evaluation',
    description: 'Decisions are made in application memory, never against a network call.',
    trace: 'in-process snapshot',
  },
  {
    title: 'Strict multi-tenancy',
    description: 'Organization → project → environment isolation, so no flag leaks across products.',
    trace: 'Org → Project → Env',
  },
];

type FlowLine = { value: string; reason?: string };
type FlowExit = { label: string; tone: 'go' | 'stop'; lines: FlowLine[] };

const GATES: Array<{ question: string; note: string; exits: FlowExit[] }> = [
  {
    question: 'Is the kill switch engaged?',
    note: 'Checked before any rule or percentage.',
    exits: [
      { label: 'engaged', tone: 'stop', lines: [{ value: 'false', reason: 'KILL_SWITCH_ACTIVE' }] },
      { label: 'clear', tone: 'go', lines: [{ value: 'continue' }] },
    ],
  },
  {
    question: 'Is the flag enabled for all users?',
    note: 'The audience override beats every rule below it.',
    exits: [
      { label: 'yes', tone: 'stop', lines: [{ value: 'true', reason: 'ENABLE_ALL_USERS' }] },
      { label: 'no', tone: 'go', lines: [{ value: 'continue' }] },
    ],
  },
  {
    question: 'Does a targeting rule match?',
    note: 'Rules run by ascending priority; conditions are ANDed.',
    exits: [
      { label: 'matched', tone: 'go', lines: [{ value: 'continue' }] },
      { label: 'no match', tone: 'stop', lines: [{ value: 'false', reason: 'DEFAULT_VALUE' }] },
    ],
  },
  {
    question: 'Is the user inside the rollout bucket?',
    note: 'bucket = Murmur3(flag_key:user_id) % 100, sticky for that user.',
    exits: [
      {
        label: 'inside',
        tone: 'go',
        lines: [
          { value: 'rule value', reason: 'RULE_AND_ROLLOUT' },
          { value: 'true', reason: 'PERCENTAGE_ROLLOUT' },
        ],
      },
      {
        label: 'outside',
        tone: 'stop',
        lines: [
          { value: 'opposite', reason: 'RULE_OUTSIDE_ROLLOUT' },
          { value: 'false', reason: 'PERCENTAGE_OUTSIDE_ROLLOUT' },
        ],
      },
    ],
  },
];

const STEPS = [
  ['01', 'Create an organization', 'Give your team a home for every product surface.'],
  ['02', 'Create a project', 'Start with isolated dev, staging, and prod environments.'],
  ['03', 'Add feature flags', 'Shape a rollout with rules, a percentage, and a kill switch.'],
  ['04', 'Evaluate with confidence', 'Connect your app and ship only to the right audience.'],
];

export function LandingPage() {
  return (
    <div className="landing-page">
      <header className="landing-nav">
        <Link className="landing-brand" to="/">
          <span className="brand-logo">C</span>
          <span>
            <strong>Catalyst</strong>
            <small>Feature control plane</small>
          </span>
        </Link>
        <nav className="landing-nav-links" aria-label="Public navigation">
          <a href="#problem">Problem</a>
          <a href="#capabilities">Capabilities</a>
          <a href="#architecture">Architecture</a>
          <a href="#how-it-works">How it works</a>
          <Link className="btn-gold-outline" to="/login">Sign in</Link>
        </nav>
      </header>

      <main>
        <section className="landing-hero">
          <div className="hero-orbit orbit-one" aria-hidden="true" />
          <div className="hero-orbit orbit-two" aria-hidden="true" />
          <div className="hero-grid-mark" aria-hidden="true" />
          <div className="hero-copy">
            <span className="eyebrow hero-eyebrow">The calm layer between idea and impact</span>
            <h1 aria-label="Ship features with confidence">Ship features<br /><em>with confidence</em></h1>
            <p>
              Catalyst gives product teams a precise, observable control plane for feature flags,
              gradual rollouts, and emergency decisions — without slowing down delivery.
            </p>
            <div className="hero-actions">
              <Link className="btn-primary btn-large" to="/app">Get Started <span aria-hidden="true">→</span></Link>
              <a className="btn-gold-outline btn-large" href="/docs">View Docs <span aria-hidden="true">→</span></a>
            </div>
            <div className="hero-proof">
              <span className="proof-line" />
              <span>Built for teams that refuse to guess</span>
            </div>
          </div>
          <div className="hero-console" aria-label="Catalyst rollout preview">
            <div className="console-glow" aria-hidden="true" />
            <div className="console-window">
              <div className="console-bar"><span /><span /><span /><small>checkout-service / prod</small></div>
              <div className="console-body">
                <div className="console-title-row"><span>Feature flags</span><span className="console-live"><i /> Live</span></div>
                <div className="console-flag-row console-flag-highlight">
                  <div><strong>new-checkout-v2</strong><small>Gradual rollout</small></div>
                  <div className="console-progress"><span style={{ width: '72%' }} /></div>
                  <b>72%</b>
                </div>
                <div className="console-flag-row">
                  <div><strong>instant-search</strong><small>Targeted beta</small></div>
                  <div className="console-status-pill">Active</div>
                  <b>100%</b>
                </div>
                <div className="console-flag-row console-flag-killed">
                  <div><strong>legacy-pricing</strong><small>Emergency switch</small></div>
                  <div className="console-status-pill killed">Killed</div>
                  <b>—</b>
                </div>
                <div className="console-footer"><span>ETag: W/&quot;a4f2:prod:18&quot;</span><span>synced just now</span></div>
              </div>
            </div>
            <div className="console-float-card float-safe"><span className="float-icon">✓</span><span><strong>Safe by default</strong><small>Every flag has a fallback</small></span></div>
            <div className="console-float-card float-live"><span className="pulse-ring" /><span><strong>12,842 evaluations</strong><small>and counting</small></span></div>
          </div>
        </section>

        <section className="stack-strip" aria-label="Technology stack">
          <span>Built on a modern, observable stack</span>
          <div><b>FastAPI</b><i>·</i><b>PostgreSQL</b><i>·</i><b>Redis</b><i>·</i><b>React</b></div>
        </section>

        <section className="landing-section problem-section" id="problem">
          <div className="section-intro">
            <span className="eyebrow">The problem</span>
            <h2>One deploy.<br /><em>Everyone affected.</em></h2>
            <p>
              Deploying code and releasing a feature are treated as a single event. Every deployment
              immediately impacts all users, and the release process is inflexible by construction:
            </p>
          </div>
          <div className="problem-grid">
            {PROBLEMS.map((problem, index) => (
              <article className="problem-card" key={problem.title}>
                <span className="problem-index" aria-hidden="true">0{index + 1}</span>
                <h3>{problem.title}</h3>
                <p>{problem.description}</p>
              </article>
            ))}
          </div>
        </section>

        <section className="landing-section" id="capabilities">
          <div className="section-intro">
            <span className="eyebrow">A sharper release ritual</span>
            <h2>Control the moment.<br /><em>Keep the momentum.</em></h2>
            <p>Every capability is designed to make the safe path the easy path.</p>
          </div>
          <div className="feature-grid">
            {FEATURES.map((feature, index) => (
              <article className={`feature-card feature-card-${index + 1}`} key={feature.title}>
                <span className="feature-icon" aria-hidden="true">{feature.icon}</span>
                <span className="feature-index">0{index + 1}</span>
                <h3>{feature.title}</h3>
                <p>{feature.description}</p>
                <span className="feature-arrow" aria-hidden="true">↗</span>
              </article>
            ))}
          </div>
        </section>

        <section className="landing-section objectives-section" id="objectives">
          <div className="section-intro compact">
            <span className="eyebrow">Objectives</span>
            <h2>What the system<br /><em>must do.</em></h2>
            <p>Six concrete objectives, each traceable to a feature rather than a promise.</p>
          </div>
          <ol className="objective-list">
            {OBJECTIVES.map((objective, index) => (
              <li className="objective-row" key={objective.title}>
                <span className="objective-number" aria-hidden="true">0{index + 1}</span>
                <div>
                  <h3>{objective.title}</h3>
                  <p>{objective.description}</p>
                </div>
                <span className="objective-trace">{objective.trace}</span>
              </li>
            ))}
          </ol>
        </section>

        <section className="landing-section" id="architecture">
          <div className="section-intro">
            <span className="eyebrow">Architecture</span>
            <h2>Two planes.<br /><em>One source of truth.</em></h2>
            <p>
              The control plane decides; the data plane serves those decisions from memory. Your
              app calls the SDK, the SDK pulls a versioned snapshot, and every check after that is
              local.
            </p>
          </div>
          <div className="architecture">
            <div className="arch-plane">
              <div className="arch-plane-head"><span>Data plane</span><small>inside your app</small></div>
              <div className="arch-stack">
                <div className="arch-node">
                  <strong>Application code</strong>
                  <small>is_enabled(flag_key, user_id, attributes)</small>
                </div>
                <span className="arch-arrow" aria-hidden="true">↓<em>is_enabled()</em></span>
                <div className="arch-node accent">
                  <strong>catalyst_sdk</strong>
                  <small>single-flight reads · failure backoff</small>
                </div>
                <span className="arch-arrow" aria-hidden="true">↓<em>holds</em></span>
                <div className="arch-node">
                  <strong>In-memory snapshot</strong>
                  <small>flags · rules · environment version</small>
                </div>
              </div>
            </div>
            <div className="arch-connector" aria-hidden="true">
              <small><b>GET /bootstrap</b>If-None-Match · single-flight</small>
              <span className="arch-wire arch-wire-request" />
              <small><b>200 snapshot</b>304 · nothing changed</small>
              <span className="arch-wire arch-wire-response" />
            </div>
            <div className="arch-plane">
              <div className="arch-plane-head"><span>Control plane</span><small>decides</small></div>
              <div className="arch-stack">
                <div className="arch-node">
                  <strong>React 19 Dashboard</strong>
                  <small>org · project · environment</small>
                </div>
                <span className="arch-arrow" aria-hidden="true">↓<em>JWT</em></span>
                <div className="arch-node accent">
                  <strong>FastAPI API</strong>
                  <small>evaluate · bootstrap · audit</small>
                </div>
                <span className="arch-arrow" aria-hidden="true">↓<em>read / write</em></span>
                <div className="arch-node-row">
                  <div className="arch-node">
                    <strong>PostgreSQL 16</strong>
                    <small>flags · rules · state</small>
                  </div>
                  <div className="arch-node">
                    <strong>Redis 7</strong>
                    <small>snapshot cache</small>
                  </div>
                </div>
              </div>
            </div>
          </div>
          <p className="architecture-caption">
            <span aria-hidden="true">✦</span>
            A mutation bumps the environment version, the snapshot is refetched, and the next
            request reads the new decision locally.
          </p>
        </section>

        <section className="landing-section evaluation-section" id="evaluation">
          <div className="section-intro compact">
            <span className="eyebrow">Evaluation order</span>
            <h2>Four gates.<br /><em>One boolean.</em></h2>
            <p>
              Kill switch → enable to all → rules by priority → percentage rollout. Every branch is
              deterministic, and every branch names its reason.
            </p>
          </div>
          <div className="flow">
            <div className="flow-entry">
              <b>Entry</b>
              <code>is_enabled(flag_key, user_id, attributes)</code>
            </div>
            {GATES.map((gate, index) => (
              <div className="flow-gate" key={gate.question}>
                <span className="flow-step" aria-hidden="true">0{index + 1}</span>
                <div>
                  <h3 className="flow-question">{gate.question}</h3>
                  <small>{gate.note}</small>
                </div>
                <div className="flow-exits">
                  {gate.exits.map((exit) => (
                    <div className={`flow-exit flow-exit-${exit.tone}`} key={exit.label}>
                      <b>{exit.label}</b>
                      {exit.lines.map((line) => (
                        <span key={`${line.value}-${line.reason ?? 'next'}`}>
                          <strong>{line.value}</strong>
                          {line.reason ? <> · <code>{line.reason}</code></> : null}
                        </span>
                      ))}
                    </div>
                  ))}
                </div>
              </div>
            ))}
            <div className="flow-foot">
              Every path returns a boolean and a reason code — the dashboard playground shows the
              same path for a real user.
            </div>
          </div>
        </section>

        <section className="landing-section how-section" id="how-it-works">
          <div className="section-intro compact">
            <span className="eyebrow">From zero to safely live</span>
            <h2>Four steps.<br /><em>One source of truth.</em></h2>
          </div>
          <div className="steps-list">
            {STEPS.map(([number, title, description]) => (
              <div className="step-row" key={number}>
                <span className="step-number">{number}</span>
                <div><h3>{title}</h3><p>{description}</p></div>
                <span className="step-line" aria-hidden="true">→</span>
              </div>
            ))}
          </div>
        </section>

        <section className="landing-cta">
          <div className="cta-mark" aria-hidden="true">✦</div>
          <span className="eyebrow">Your next release is ready</span>
          <h2>Make the brave thing,<br /><em>available now.</em></h2>
          <Link className="btn-primary btn-large" to="/app">Enter the workspace <span aria-hidden="true">→</span></Link>
        </section>
      </main>

      <footer className="landing-footer">
        <div className="footer-brand"><span className="brand-logo tiny">C</span><span><strong>Catalyst</strong><small>Ship with confidence.</small></span></div>
        <div className="footer-links"><a href="/docs">Documentation</a><Link to="/login">Sign in</Link><Link to="/register">Create account</Link></div>
        <small>© 2026 Catalyst. Built for thoughtful teams.</small>
      </footer>
    </div>
  );
}
