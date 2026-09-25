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

const STEPS = [
  ['01', 'Create an organization', 'Give your team a home for every product surface.'],
  ['02', 'Create a project', 'Start with isolated dev, staging, and prod environments.'],
  ['03', 'Add feature flags', 'Shape a rollout with defaults, rules, and a kill switch.'],
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
          <a href="#capabilities">Capabilities</a>
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
              <a className="btn-gold-outline btn-large" href="/docs" target="_blank" rel="noreferrer">View Docs <span aria-hidden="true">↗</span></a>
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
          <h2>Make the brave thing<br /><em>the routine thing.</em></h2>
          <Link className="btn-primary btn-large" to="/app">Enter the workspace <span aria-hidden="true">→</span></Link>
        </section>
      </main>

      <footer className="landing-footer">
        <div className="footer-brand"><span className="brand-logo tiny">C</span><span><strong>Catalyst</strong><small>Ship with confidence.</small></span></div>
        <div className="footer-links"><a href="/docs" target="_blank" rel="noreferrer">Documentation</a><Link to="/login">Sign in</Link><Link to="/register">Create account</Link></div>
        <small>© 2026 Catalyst. Built for thoughtful teams.</small>
      </footer>
    </div>
  );
}
