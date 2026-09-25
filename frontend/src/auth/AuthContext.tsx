import { createContext, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';
import { Navigate, useLocation } from 'react-router-dom';

import {
  hasRefreshToken,
  login as loginRequest,
  logout as clearSession,
  onAuthExpired,
  refreshSession,
  register as registerRequest,
} from '../api';
import type { AuthResponse, User } from '../api';

type AuthStatus = 'loading' | 'authenticated' | 'anonymous';

interface AuthContextValue {
  user: User | null;
  status: AuthStatus;
  login: (email: string, password: string) => Promise<AuthResponse>;
  register: (fullName: string, email: string, password: string) => Promise<AuthResponse>;
  logout: () => void;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [user, setUser] = useState<User | null>(null);
  const [status, setStatus] = useState<AuthStatus>('loading');

  useEffect(() => {
    let active = true;

    const restoreSession = async () => {
      if (!hasRefreshToken()) {
        if (active) setStatus('anonymous');
        return;
      }
      try {
        const response = await refreshSession();
        if (!active) return;
        if (response) {
          setUser(response.user);
          setStatus('authenticated');
        } else {
          setUser(null);
          setStatus('anonymous');
        }
      } catch {
        if (!active) return;
        setUser(null);
        setStatus('anonymous');
      }
    };

    void restoreSession();
    onAuthExpired(() => {
      if (!active) return;
      setUser(null);
      setStatus('anonymous');
    });

    return () => {
      active = false;
      onAuthExpired(null);
    };
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      user,
      status,
      login: async (email, password) => {
        const response = await loginRequest({ email, password });
        setUser(response.user);
        setStatus('authenticated');
        return response;
      },
      register: async (fullName, email, password) => {
        const response = await registerRequest({ full_name: fullName, email, password });
        setUser(response.user);
        setStatus('authenticated');
        return response;
      },
      logout: () => {
        clearSession();
        setUser(null);
        setStatus('anonymous');
      },
    }),
    [status, user],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const context = useContext(AuthContext);
  if (!context) throw new Error('useAuth must be used inside AuthProvider');
  return context;
}

export function ProtectedRoute({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  const location = useLocation();

  if (status === 'loading') {
    return (
      <div className="route-loader" role="status" aria-live="polite">
        <span className="loader-mark">C</span>
        <span>Restoring your workspace…</span>
      </div>
    );
  }
  if (status === 'anonymous') {
    return <Navigate to="/login" replace state={{ from: `${location.pathname}${location.search}` }} />;
  }
  return <>{children}</>;
}

export function PublicOnlyRoute({ children }: { children: ReactNode }) {
  const { status } = useAuth();
  if (status === 'loading') {
    return (
      <div className="route-loader" role="status" aria-live="polite">
        <span className="loader-mark">C</span>
        <span>Loading Catalyst…</span>
      </div>
    );
  }
  if (status === 'authenticated') return <Navigate to="/app" replace />;
  return <>{children}</>;
}
