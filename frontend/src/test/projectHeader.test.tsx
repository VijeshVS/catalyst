import { fireEvent, render, screen } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { ProjectHeader } from '../components/ProjectHeader';
import type { Organization, Project } from '../api';
import type { ProjectData } from '../workspace/useProject';

const PROJECT_ID = '3a33e31c-1686-4601-96db-ed8c6b3f3f44';

const organization: Organization = {
  id: 'org-1',
  name: 'Acme Labs',
  description: null,
  owner_id: 'user-1',
  created_at: '2026-01-01T00:00:00Z',
  projects: [],
};

const project: Project = {
  id: PROJECT_ID,
  org_id: 'org-1',
  name: 'Checkout',
  created_at: '2026-01-01T00:00:00Z',
  environments: [],
};

const projectData = {
  flags: [{ key: 'a' }, { key: 'b' }],
  environments: [{ id: 'e1', project_id: PROJECT_ID, name: 'dev', version: 3 }],
  activeEnv: 'dev',
  setActiveEnv: vi.fn(),
} as unknown as ProjectData;

function renderHeader() {
  return render(
    <MemoryRouter
      initialEntries={[`/app/orgs/org-1/projects/${PROJECT_ID}`]}
      future={{ v7_startTransition: true, v7_relativeSplatPath: true }}
    >
      <ProjectHeader
        organization={organization}
        project={project}
        projectData={projectData}
      />
    </MemoryRouter>,
  );
}

function mockClipboard(writeText: (text: string) => Promise<void>) {
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText },
    configurable: true,
    writable: true,
  });
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('ProjectHeader project id copy', () => {
  it('shows only the live project sections, with no placeholder tabs', () => {
    renderHeader();
    const tabs = screen.getAllByRole('link').map((link) => link.textContent?.trim());
    const projectTabs = tabs.filter((label) =>
      ['Feature Flags', 'Environments', 'API Keys'].includes(label ?? ''),
    );
    expect(projectTabs).toEqual(['Feature Flags', 'Environments', 'API Keys']);
    // The unimplemented sections must not be advertised.
    expect(screen.queryByText(/Audit Log/i)).not.toBeInTheDocument();
    expect(screen.queryByText(/^Settings$/i)).not.toBeInTheDocument();
  });

  it('shows the project id so it can be read without selecting text', () => {
    renderHeader();
    expect(screen.getByText('Project ID')).toBeInTheDocument();
    expect(screen.getByText(PROJECT_ID)).toBeInTheDocument();
  });

  it('copies the project id to the clipboard and confirms it', async () => {
    const writeText = vi.fn(async () => {});
    mockClipboard(writeText);
    renderHeader();

    const button = screen.getByRole('button', { name: /project id/i });
    expect(button).toHaveTextContent('Copy');

    fireEvent.click(button);

    expect(writeText).toHaveBeenCalledWith(PROJECT_ID);
    await vi.waitFor(() => {
      expect(button).toHaveTextContent('Copied');
    });
    expect(button).toHaveAttribute('data-copied', 'true');
  });

  it('does not claim success when the clipboard is unavailable', async () => {
    mockClipboard(vi.fn(async () => {
      throw new Error('denied');
    }));
    renderHeader();

    const button = screen.getByRole('button', { name: /project id/i });
    fireEvent.click(button);

    await vi.waitFor(() => {
      expect(button).toHaveTextContent('Copy');
    });
    expect(button).toHaveAttribute('data-copied', 'false');
  });
});
