import { useState } from 'react';
import { Link, useLocation, useNavigate } from 'react-router-dom';
import type { FormEvent } from 'react';

import { getErrorMessage } from '../api';
import { AuthFrame } from '../components/AuthFrame';
import { useAuth } from '../auth/AuthContext';

function destinationFromState(state: unknown): string {
  if (typeof state === 'object' && state !== null && 'from' in state) {
    const from = (state as { from?: unknown }).from;
    if (typeof from === 'string' && from.startsWith('/app')) return from;
  }
  return '/app';
}

export function LoginPage() {
  const { login } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    setBusy(true);
    setError(null);
    try {
      await login(email.trim(), password);
      navigate(destinationFromState(location.state), { replace: true });
    } catch (requestError) {
      setError(getErrorMessage(requestError, 'Unable to sign in'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthFrame
      eyebrow="Welcome back"
      title="Return to your control room."
      subtitle="Sign in to manage rollouts, environments, and the next safe release."
    >
      <form className="auth-form" onSubmit={submit}>
        <div className="form-group">
          <label className="form-label" htmlFor="login-email">Email address</label>
          <input
            id="login-email"
            className="form-input"
            type="email"
            autoComplete="email"
            required
            placeholder="you@company.com"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
          />
        </div>
        <div className="form-group">
          <div className="label-row"><label className="form-label" htmlFor="login-password">Password</label><span className="form-hint">8+ characters</span></div>
          <input
            id="login-password"
            className="form-input"
            type="password"
            autoComplete="current-password"
            required
            placeholder="Your password"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>
        {error && <div className="form-error" role="alert">{error}</div>}
        <button type="submit" className="btn-primary auth-submit" disabled={busy}>
          {busy ? 'Signing in…' : 'Sign in'} <span aria-hidden="true">→</span>
        </button>
      </form>
      <p className="auth-switch">Don’t have an account? <Link to="/register">Register</Link></p>
    </AuthFrame>
  );
}
