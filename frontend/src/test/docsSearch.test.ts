import { describe, expect, it } from 'vitest';

import { matchCount, normalizeQuery, searchSections } from '../lib/docsSearch';
import type { DocsSection } from '../lib/docsSearch';

const SECTIONS: DocsSection[] = [
  { id: 'quickstart', label: 'Quick start', summary: 'Construct a client.', keywords: ['setup'] },
  { id: 'host', label: 'Choosing the API host', summary: 'The hosted API is the default.', keywords: ['base url', 'onrender'] },
  { id: 'caching', label: 'Server-side caching', summary: 'Redis serves snapshots.', keywords: ['redis', 'ttl'] },
];

describe('normalizeQuery', () => {
  it('lowercases and splits on whitespace', () => {
    expect(normalizeQuery('  Redis   TTL ')).toEqual(['redis', 'ttl']);
  });

  it('returns nothing for an empty query', () => {
    expect(normalizeQuery('   ')).toEqual([]);
  });
});

describe('searchSections', () => {
  it('returns every section when nothing has been typed', () => {
    expect(searchSections(SECTIONS, '')).toEqual(SECTIONS);
    expect(searchSections(SECTIONS, '   ')).toEqual(SECTIONS);
  });

  it('matches on the label', () => {
    expect(searchSections(SECTIONS, 'host').map((section) => section.id)).toEqual(['host']);
  });

  it('matches on the summary', () => {
    expect(searchSections(SECTIONS, 'redis').map((section) => section.id)).toEqual(['caching']);
  });

  it('matches on keywords a reader would try', () => {
    expect(searchSections(SECTIONS, 'onrender').map((section) => section.id)).toEqual(['host']);
    expect(searchSections(SECTIONS, 'base url').map((section) => section.id)).toEqual(['host']);
  });

  it('is case insensitive and ignores surrounding whitespace', () => {
    expect(searchSections(SECTIONS, '  REDIS ').map((section) => section.id)).toEqual(['caching']);
  });

  it('requires every term to match', () => {
    expect(searchSections(SECTIONS, 'redis ttl').map((section) => section.id)).toEqual(['caching']);
    expect(searchSections(SECTIONS, 'redis host')).toEqual([]);
  });

  it('preserves document order', () => {
    // "de" appears in the host and caching sections, not the first one.
    expect(searchSections(SECTIONS, 'de').map((section) => section.id)).toEqual([
      'host',
      'caching',
    ]);
  });

  it('returns nothing for a term that appears nowhere', () => {
    expect(searchSections(SECTIONS, 'kubernetes')).toEqual([]);
  });
});

describe('matchCount', () => {
  it('counts how many terms a section matches', () => {
    expect(matchCount(SECTIONS[2], 'redis')).toBe(1);
    expect(matchCount(SECTIONS[2], 'redis ttl')).toBe(2);
    expect(matchCount(SECTIONS[2], 'redis redis-cache')).toBe(1);
    expect(matchCount(SECTIONS[0], '')).toBe(0);
  });
});
