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

export function RegisterPage() {
  const { register } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();
  const [fullName, setFullName] = useState('');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [confirmPassword, setConfirmPassword] = useState('');
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    if (password.length < 8) {
      setError('Password must be at least 8 characters.');
      return;
    }
    if (password !== confirmPassword) {
      setError('Passwords do not match.');
      return;
    }
    setBusy(true);
    setError(null);
    try {
      await register(fullName.trim(), email.trim(), password);
      navigate(destinationFromState(location.state), { replace: true });
    } catch (requestError) {
      setError(getErrorMessage(requestError, 'Unable to create your account'));
    } finally {
      setBusy(false);
    }
  };

  return (
    <AuthFrame
      eyebrow="Start shipping clearly"
      title="Build your workspace."
      subtitle="Create an account, then give your team a safer way to release every feature."
    >
      <form className="auth-form" onSubmit={submit}>
        <div className="form-group">
          <label className="form-label" htmlFor="register-name">Full name</label>
          <input
            id="register-name"
            className="form-input"
            type="text"
            autoComplete="name"
            required
            placeholder="Alex Morgan"
            value={fullName}
            onChange={(event) => setFullName(event.target.value)}
          />
        </div>
        <div className="form-group">
          <label className="form-label" htmlFor="register-email">Email address</label>
          <input
            id="register-email"
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
          <label className="form-label" htmlFor="register-password">Password</label>
          <input
            id="register-password"
            className="form-input"
            type="password"
            autoComplete="new-password"
            minLength={8}
            required
            placeholder="At least 8 characters"
            value={password}
            onChange={(event) => setPassword(event.target.value)}
          />
        </div>
        <div className="form-group">
          <label className="form-label" htmlFor="register-confirm">Confirm password</label>
          <input
            id="register-confirm"
            className="form-input"
            type="password"
            autoComplete="new-password"
            minLength={8}
            required
            placeholder="Repeat your password"
            value={confirmPassword}
            onChange={(event) => setConfirmPassword(event.target.value)}
          />
        </div>
        {error && <div className="form-error" role="alert">{error}</div>}
        <button type="submit" className="btn-primary auth-submit" disabled={busy}>
          {busy ? 'Creating account…' : 'Create account'} <span aria-hidden="true">→</span>
        </button>
      </form>
      <p className="auth-switch">Already have an account? <Link to="/login">Sign in</Link></p>
    </AuthFrame>
  );
}
