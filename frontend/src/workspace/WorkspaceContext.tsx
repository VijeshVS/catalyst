import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react';
import type { ReactNode } from 'react';

import {
  createOrganization as createOrganizationRequest,
  createProject as createProjectRequest,
  fetchOrganizations,
  getErrorMessage,
} from '../api';
import type { Organization, Project } from '../api';
import { useAuth } from '../auth/AuthContext';

const LAST_ORG_KEY = 'catalyst.lastOrganizationId';

interface WorkspaceContextValue {
  organizations: Organization[];
  projects: Project[];
  selectedOrgId: string | null;
  selectedOrg: Organization | null;
  loading: boolean;
  error: string | null;
  refreshOrganizations: () => Promise<Organization[]>;
  createOrganization: (name: string, description?: string) => Promise<Organization>;
  createProject: (orgId: string, name: string) => Promise<Project>;
  selectOrganization: (orgId: string) => void;
  getOrganization: (orgId: string | undefined) => Organization | null;
}

const WorkspaceContext = createContext<WorkspaceContextValue | null>(null);

function readLastOrganizationId(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage.getItem(LAST_ORG_KEY);
  } catch {
    return null;
  }
}

function writeLastOrganizationId(orgId: string): void {
  if (typeof window === 'undefined') return;
  try {
    window.localStorage.setItem(LAST_ORG_KEY, orgId);
  } catch {
    // The workspace remains usable if storage is unavailable.
  }
}

export function WorkspaceProvider({ children }: { children: ReactNode }) {
  const { user } = useAuth();
  const [organizations, setOrganizations] = useState<Organization[]>([]);
  const [selectedOrgId, setSelectedOrgId] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const refreshOrganizations = useCallback(async (): Promise<Organization[]> => {
    if (!user) {
      setOrganizations([]);
      setSelectedOrgId(null);
      setLoading(false);
      return [];
    }

    setLoading(true);
    try {
      const data = await fetchOrganizations();
      setOrganizations(data);
      setError(null);
      setSelectedOrgId((previous) => {
        if (previous && data.some((organization) => organization.id === previous)) return previous;
        const remembered = readLastOrganizationId();
        if (remembered && data.some((organization) => organization.id === remembered)) {
          return remembered;
        }
        return data[0]?.id ?? null;
      });
      return data;
    } catch (requestError) {
      setError(getErrorMessage(requestError, 'Failed to load organizations'));
      return [];
    } finally {
      setLoading(false);
    }
  }, [user]);

  useEffect(() => {
    // Defer the initial synchronization out of the effect commit so a
    // restored session does not cause a cascading render.
    const timer = window.setTimeout(() => {
      void refreshOrganizations();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [refreshOrganizations]);

  const selectOrganization = useCallback((orgId: string) => {
    setSelectedOrgId(orgId);
    writeLastOrganizationId(orgId);
  }, []);

  const createOrganization = useCallback(
    async (name: string, description?: string): Promise<Organization> => {
      const organization = await createOrganizationRequest(name, description);
      setOrganizations((previous) => [...previous, organization]);
      setSelectedOrgId(organization.id);
      writeLastOrganizationId(organization.id);
      setError(null);
      return organization;
    },
    [],
  );

  const createProject = useCallback(async (orgId: string, name: string): Promise<Project> => {
    const project = await createProjectRequest(orgId, name);
    setOrganizations((previous) =>
      previous.map((organization) =>
        organization.id === orgId
          ? { ...organization, projects: [...organization.projects, project] }
          : organization,
      ),
    );
    return project;
  }, []);

  const value = useMemo<WorkspaceContextValue>(
    () => {
      const selectedOrg = organizations.find((organization) => organization.id === selectedOrgId) ?? null;
      return {
        organizations,
        projects: selectedOrg?.projects ?? [],
        selectedOrgId,
        selectedOrg,
        loading,
        error,
        refreshOrganizations,
        createOrganization,
        createProject,
        selectOrganization,
        getOrganization: (orgId) => organizations.find((organization) => organization.id === orgId) ?? null,
      };
    },
    [
      organizations,
      selectedOrgId,
      loading,
      error,
      refreshOrganizations,
      createOrganization,
      createProject,
      selectOrganization,
    ],
  );

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}

export function useWorkspace(): WorkspaceContextValue {
  const context = useContext(WorkspaceContext);
  if (!context) throw new Error('useWorkspace must be used inside WorkspaceProvider');
  return context;
}
