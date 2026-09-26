/**
 * Search over the SDK documentation sections.
 *
 * Kept out of the page component so the matching rules can be unit tested
 * without rendering anything.
 */

export interface DocsSection {
  id: string;
  label: string;
  /** One-line summary, also indexed so a search can match on meaning. */
  summary: string;
  /** Extra terms a reader might type that do not appear in the label. */
  keywords: string[];
}

export function normalizeQuery(query: string): string[] {
  return query
    .toLowerCase()
    .split(/\s+/)
    .map((term) => term.trim())
    .filter(Boolean);
}

/**
 * Returns the sections matching every term, in document order.
 *
 * An empty query matches everything, which is what the table of contents shows
 * before anyone types.
 */
export function searchSections(sections: DocsSection[], query: string): DocsSection[] {
  const terms = normalizeQuery(query);
  if (terms.length === 0) return sections;

  return sections.filter((section) => {
    const haystack = [section.label, section.summary, ...section.keywords]
      .join(' ')
      .toLowerCase();
    return terms.every((term) => haystack.includes(term));
  });
}

/** Counts how many of the query's terms a section matches, for ranking feedback. */
export function matchCount(section: DocsSection, query: string): number {
  const terms = normalizeQuery(query);
  if (terms.length === 0) return 0;
  const haystack = [section.label, section.summary, ...section.keywords]
    .join(' ')
    .toLowerCase();
  return terms.filter((term) => haystack.includes(term)).length;
}
