import { useState } from 'react';
import { useNavigate } from 'react-router-dom';

import { useAuth } from '../auth/AuthContext';

function initials(name: string, email: string): string {
  const source = name.trim() || email;
  const parts = source.split(/\s+/).filter(Boolean);
  if (parts.length > 1) return `${parts[0][0]}${parts[1][0]}`.toUpperCase();
  return source.slice(0, 2).toUpperCase();
}

export function UserMenu() {
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  if (!user) return null;

  const signOut = () => {
    logout();
    setOpen(false);
    navigate('/login', { replace: true });
  };

  return (
    <div className="user-menu">
      <button
        type="button"
        className="user-menu-trigger"
        onClick={() => setOpen((previous) => !previous)}
        aria-expanded={open}
        aria-haspopup="menu"
      >
        <span className="user-avatar">{initials(user.full_name, user.email)}</span>
        <span className="user-menu-name">{user.full_name || user.email}</span>
        <span className="user-chevron" aria-hidden="true">⌄</span>
      </button>
      {open && (
        <div className="user-menu-popover" role="menu">
          <div className="user-menu-heading" aria-label={`Signed in as ${user.email}`}>
            <span className="eyebrow">Signed in as</span>
            <strong>{user.email}</strong>
          </div>
          <button type="button" className="user-menu-action" role="menuitem" onClick={signOut}>
            <span aria-hidden="true">↪</span> Log out
          </button>
        </div>
      )}
    </div>
  );
}
