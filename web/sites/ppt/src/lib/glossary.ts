import { getCollection, type CollectionEntry } from "astro:content";
import sourceData from "../data/sources.json";

export type Term = CollectionEntry<"glossary">;

export interface Source {
  title: string;
  publisher: string;
  url: string;
  kind?: string;
  retrieved?: string;
  note?: string;
}

const SOURCES = sourceData.sources as Record<string, Source>;

export const CATEGORIES = [
  { key: "futures", label: "Futures & contracten" },
  { key: "handel", label: "Handel & uitvoering" },
  { key: "risico", label: "Risico & statistiek" },
  { key: "propfirms", label: "Prop firms" },
  { key: "regels", label: "Regelgeving & toezicht" },
  { key: "emigratie", label: "Emigratie & fiscaal" },
] as const;

export const categoryLabel = (key: string): string =>
  CATEGORIES.find((c) => c.key === key)?.label ?? key;

/** Published terms, alphabetical by the term itself rather than by slug. */
export async function allTerms(): Promise<Term[]> {
  const terms = await getCollection("glossary", ({ data }) => !data.draft);
  return terms.sort((a, b) => a.data.term.localeCompare(b.data.term, "nl"));
}

/**
 * Resolve source ids to full citations.
 *
 * An unknown id is dropped rather than rendered as a broken entry — but it is
 * reported, because a citation that silently disappears is worse than one that
 * is obviously missing.
 */
export function resolveSources(ids: string[]): Source[] {
  return ids
    .map((id) => {
      const source = SOURCES[id];
      if (!source) {
        console.warn(`[begrippenlijst] onbekende bron-id: ${id}`);
        return null;
      }
      return source;
    })
    .filter((s): s is Source => s !== null);
}

/** Terms listed under `related`, resolved to real entries and de-duplicated. */
export function resolveRelated(term: Term, all: Term[]): Term[] {
  const byId = new Map(all.map((t) => [t.id, t]));
  const seen = new Set<string>();
  const out: Term[] = [];

  for (const slug of term.data.related) {
    const found = byId.get(slug);
    if (!found) {
      console.warn(`[begrippenlijst] ${term.id} verwijst naar onbekend begrip: ${slug}`);
      continue;
    }
    if (found.id === term.id || seen.has(found.id)) continue;
    seen.add(found.id);
    out.push(found);
  }

  return out;
}

/** Terms that link TO this one but are not listed in its own `related`. */
export function backlinks(term: Term, all: Term[]): Term[] {
  const own = new Set(term.data.related);
  return all.filter(
    (candidate) =>
      candidate.id !== term.id &&
      candidate.data.related.includes(term.id) &&
      !own.has(candidate.id)
  );
}

/** Alphabetical buckets for the A–Z rail on the index. */
export function byLetter(terms: Term[]): { letter: string; terms: Term[] }[] {
  const buckets = new Map<string, Term[]>();
  for (const term of terms) {
    const letter = term.data.term.charAt(0).toUpperCase();
    buckets.set(letter, [...(buckets.get(letter) ?? []), term]);
  }
  return [...buckets.entries()]
    .map(([letter, items]) => ({ letter, terms: items }))
    .sort((a, b) => a.letter.localeCompare(b.letter, "nl"));
}

/** Compact payload the client-side filter searches over. */
export function searchIndex(terms: Term[]) {
  return terms.map((t) => ({
    id: t.id,
    haystack: [t.data.term, t.data.short, ...t.data.aliases]
      .join(" ")
      .toLowerCase(),
  }));
}
