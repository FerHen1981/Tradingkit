import { getCollection, type CollectionEntry } from "astro:content";

export type Guide = CollectionEntry<"guides">;

export const TOPICS = [
  { key: "emigratie", label: "Emigratie", blurb: "Verhuizen, woonplaats en papierwerk." },
  { key: "trading", label: "Trading", blurb: "Uitvoering, risico en het meten daarvan." },
  { key: "bedrijf", label: "Bedrijf & structuur", blurb: "Entiteit, vestiging en aanwezigheid." },
  { key: "geld", label: "Geld & administratie", blurb: "Bankrelatie, kosten en boekhouding." },
] as const;

export const LEVELS = [
  { key: "start", label: "Start hier" },
  { key: "verdieping", label: "Verdieping" },
  { key: "gevorderd", label: "Gevorderd" },
] as const;

export const topicLabel = (key: string): string =>
  TOPICS.find((t) => t.key === key)?.label ?? key;

export const levelLabel = (key: string): string =>
  LEVELS.find((l) => l.key === key)?.label ?? key;

/** Published guides in reading order. */
export async function allGuides(): Promise<Guide[]> {
  const guides = await getCollection("guides", ({ data }) => !data.draft);
  return guides.sort((a, b) => a.data.order - b.data.order);
}

export const guidePath = (guide: Guide): string => `/gidsen/${guide.id}`;

export function byTopic(guides: Guide[]): { key: string; label: string; blurb: string; guides: Guide[] }[] {
  return TOPICS.map((topic) => ({
    ...topic,
    guides: guides.filter((g) => g.data.topic === topic.key),
  })).filter((group) => group.guides.length > 0);
}

/**
 * Neighbours in the reading path.
 *
 * Deliberately based on the global order rather than on the topic, because the
 * path is meant to be walkable end to end by somebody who does not yet know
 * which topic their question belongs to.
 */
export function neighbours(guide: Guide, all: Guide[]) {
  const index = all.findIndex((g) => g.id === guide.id);
  return {
    previous: index > 0 ? all[index - 1] : null,
    next: index >= 0 && index < all.length - 1 ? all[index + 1] : null,
  };
}
