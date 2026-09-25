import { useState } from 'react';
import { NavLink, useNavigate, useParams } from 'react-router-dom';

import { useWorkspace } from '../workspace/WorkspaceContext';

function initial(name: string): string {
  return name.trim().slice(0, 1).toUpperCase() || 'C';
}

export function Sidebar() {
  const { organizations, selectedOrg, selectedOrgId, selectOrganization } = useWorkspace();
  const { orgId, projectId } = useParams();
  const navigate = useNavigate();
  const [switcherOpen, setSwitcherOpen] = useState(false);
  const routeOrg = organizations.find((organization) => organization.id === orgId) ?? selectedOrg;
  const activeOrgId = routeOrg?.id ?? selectedOrgId;

  const changeOrganization = (nextId: string) => {
    if (!nextId) return;
    selectOrganization(nextId);
    setSwitcherOpen(false);
    navigate(`/app/orgs/${nextId}`);
  };

  return (
    <aside className="app-sidebar">
      <div className="sidebar-top">
        <div className="sidebar-label">Workspace</div>
        {routeOrg ? (
          <div className="sidebar-org">
            <span className="org-avatar">{initial(routeOrg.name)}</span>
            <span className="sidebar-org-copy">
              <strong>{routeOrg.name}</strong>
              <small>{routeOrg.projects.length} project{routeOrg.projects.length === 1 ? '' : 's'}</small>
            </span>
          </div>
        ) : (
          <div className="sidebar-org sidebar-org-placeholder">
            <span className="org-avatar">C</span>
            <span className="sidebar-org-copy"><strong>Your workspace</strong><small>Choose an organization</small></span>
          </div>
        )}

        <nav className="sidebar-nav" aria-label="Workspace navigation">
          <NavLink
            to={activeOrgId ? `/app/orgs/${activeOrgId}` : '/app'}
            className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''}`}
          >
            <span className="sidebar-link-icon" aria-hidden="true">▦</span>
            <span>Projects</span>
          </NavLink>
          <NavLink
            to={activeOrgId && projectId ? `/app/orgs/${activeOrgId}/projects/${projectId}/settings` : '#'}
            className={({ isActive }) => `sidebar-link ${isActive ? 'active' : ''} ${!projectId ? 'disabled' : ''}`}
            onClick={(event) => {
              if (!projectId) event.preventDefault();
            }}
            aria-disabled={!projectId}
          >
            <span className="sidebar-link-icon" aria-hidden="true">⚙</span>
            <span>Settings</span>
            <small className="coming-soon-label">Soon</small>
          </NavLink>
        </nav>
      </div>

      <div className="sidebar-bottom">
        <div className="sidebar-label">Organizations</div>
        <div className="org-switcher">
          <button
            type="button"
            className="org-switcher-trigger"
            onClick={() => setSwitcherOpen((previous) => !previous)}
            aria-expanded={switcherOpen}
          >
            <span className="org-switcher-current">
              <span className="org-avatar tiny">{initial(routeOrg?.name ?? 'Catalyst')}</span>
              <span>{routeOrg?.name ?? 'Select organization'}</span>
            </span>
            <span aria-hidden="true">⌄</span>
          </button>
          {switcherOpen && (
            <div className="org-switcher-menu">
              {organizations.map((organization) => (
                <button
                  type="button"
                  key={organization.id}
                  className={organization.id === activeOrgId ? 'selected' : ''}
                  onClick={() => changeOrganization(organization.id)}
                >
                  <span className="org-avatar tiny">{initial(organization.name)}</span>
                  <span>{organization.name}</span>
                </button>
              ))}
              <div className="org-switcher-divider" />
              <button type="button" className="new-org-option" onClick={() => navigate('/app/orgs/new')}>
                <span className="plus-mark">+</span> New organization
              </button>
            </div>
          )}
        </div>
        <div className="sidebar-route-note">
          <span className="sidebar-status-dot" /> All systems operational
        </div>
      </div>
    </aside>
  );
}
