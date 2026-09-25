import { Link } from 'react-router-dom';
import type { ReactNode } from 'react';

interface AuthFrameProps {
  eyebrow: string;
  title: string;
  subtitle: string;
  children: ReactNode;
}

export function AuthFrame({ eyebrow, title, subtitle, children }: AuthFrameProps) {
  return (
    <div className="auth-page">
      <div className="auth-backdrop" aria-hidden="true"><span /><span /><span /></div>
      <header className="auth-header">
        <Link className="landing-brand" to="/">
          <span className="brand-logo">C</span>
          <span><strong>Catalyst</strong><small>Feature control plane</small></span>
        </Link>
        <Link className="auth-back-link" to="/">← Back to home</Link>
      </header>
      <main className="auth-main">
        <section className="auth-card">
          <div className="auth-card-glow" aria-hidden="true" />
          <div className="auth-card-heading">
            <span className="eyebrow">{eyebrow}</span>
            <h1>{title}</h1>
            <p>{subtitle}</p>
          </div>
          {children}
          <div className="auth-card-footer">
            <span className="auth-lock" aria-hidden="true">⌁</span>
            <span>Your workspace is private to your account.</span>
          </div>
        </section>
      </main>
      <footer className="auth-footer">Catalyst <span>·</span> Ship features with confidence.</footer>
    </div>
  );
}
