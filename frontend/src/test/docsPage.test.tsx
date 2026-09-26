import { fireEvent, render, screen, within } from '@testing-library/react';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';

import { DocsPage } from '../pages/DocsPage';

function renderDocs() {
  return render(
    <MemoryRouter future={{ v7_startTransition: true, v7_relativeSplatPath: true }}>
      <DocsPage />
    </MemoryRouter>,
  );
}

/** The section links in the sidebar, which double as the search results. */
function tocLinks(): string[] {
  const toc = screen.getByRole('navigation', { name: 'Documentation sections' });
  return within(toc)
    .queryAllByRole('link')
    .map((link) => link.textContent?.trim() ?? '');
}

describe('DocsPage search', () => {
  it('lists every section before a search', () => {
    renderDocs();
    expect(screen.getByText('On this page')).toBeInTheDocument();
    expect(tocLinks()).toContain('Quick start');
    expect(tocLinks()).toContain('Error handling');
  });

  it('narrows the list to the matching sections', () => {
    renderDocs();
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'redis' } });

    expect(tocLinks()).toEqual(['Server-side caching']);
    expect(screen.getByText('1 matching section')).toBeInTheDocument();
  });

  it('finds a section by a term that is not in its title', () => {
    renderDocs();
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'onrender' } });
    expect(tocLinks()).toEqual(['Choosing the API host']);
  });

  it('reports when nothing matches', () => {
    renderDocs();
    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'kubernetes' } });

    expect(tocLinks()).toEqual([]);
    expect(screen.getByText('No matching sections')).toBeInTheDocument();
  });

  it('jumps to the first match when the search button is used', () => {
    const scrollIntoView = vi.fn();
    Element.prototype.scrollIntoView = scrollIntoView;
    renderDocs();

    fireEvent.change(screen.getByRole('searchbox'), { target: { value: 'redis' } });
    fireEvent.click(screen.getByRole('button', { name: 'Go' }));

    expect(scrollIntoView).toHaveBeenCalled();
    expect(screen.getByRole('link', { name: 'Server-side caching' })).toHaveAttribute(
      'aria-current',
      'true',
    );
  });

  it('clears the search with Escape', () => {
    renderDocs();
    const input = screen.getByRole('searchbox');

    fireEvent.change(input, { target: { value: 'redis' } });
    expect(tocLinks()).toEqual(['Server-side caching']);

    fireEvent.keyDown(input, { key: 'Escape' });
    expect(tocLinks()).toContain('Quick start');
    expect(screen.getByText('On this page')).toBeInTheDocument();
  });
});

describe('DocsPage content', () => {
  it('documents the hosted API as the default', () => {
    renderDocs();
    expect(screen.getByText(/calls the hosted Catalyst API by default/i)).toBeInTheDocument();
    expect(screen.getAllByText('CATALYST_HOST').length).toBeGreaterThan(0);
  });

  it('documents the conditional read and the server cache', () => {
    renderDocs();
    expect(screen.getByText(/Conditional read\./)).toBeInTheDocument();
    expect(screen.getByText(/Version-driven invalidation\./)).toBeInTheDocument();
  });

  it('no longer claims evaluation performs no I/O', () => {
    renderDocs();
    expect(screen.queryByText('The hot path. Never performs I/O.')).not.toBeInTheDocument();
  });
});
