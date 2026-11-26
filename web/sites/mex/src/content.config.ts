import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";

/**
 * Content collections mirror the Keystatic schema in keystatic.config.ts
 * one-to-one. Keystatic writes the files; Astro validates and renders them.
 * When you add a field, add it in both places or the build will tell you.
 */

/**
 * The homepage is a Keystatic singleton, but Astro has no singleton concept —
 * so it is modelled as a one-entry collection over the same directory. Both
 * tools then read and write exactly the same file.
 */
const homepage = defineCollection({
  loader: glob({ pattern: "index.mdx", base: "./src/content/homepage" }),
  schema: z.object({
    eyebrow: z.string().optional(),
    headline: z.string(),
    lead: z.string(),
    primaryCta: z.object({ label: z.string(), href: z.string() }).optional(),
    secondaryCta: z.object({ label: z.string(), href: z.string() }).optional(),
    statsIntro: z.string().optional(),
  }),
});

const pages = defineCollection({
  loader: glob({ pattern: "**/*.mdx", base: "./src/content/pages" }),
  schema: z.object({
    title: z.string(),
    description: z.string(),
    eyebrow: z.string().optional(),
    lead: z.string().optional(),
    /** Lower sorts first in any generated listing. */
    order: z.number().default(100),
    draft: z.boolean().default(false),
    noindex: z.boolean().default(false),
  }),
});

/** The Curaçao transition, told as a timeline. */
const journey = defineCollection({
  loader: glob({ pattern: "**/*.mdx", base: "./src/content/journey" }),
  schema: z.object({
    title: z.string(),
    date: z.coerce.date(),
    summary: z.string(),
    /** Short label on the timeline marker, e.g. "Fase 1". */
    phase: z.string().optional(),
    status: z.enum(["done", "running", "planned"]).default("done"),
    draft: z.boolean().default(false),
  }),
});

/** What the company does — the service/pillar cards on the home page. */
const pillars = defineCollection({
  loader: glob({ pattern: "**/*.mdx", base: "./src/content/pillars" }),
  schema: z.object({
    title: z.string(),
    summary: z.string(),
    order: z.number().default(100),
    /** Emoji or short mark shown above the title. */
    mark: z.string().optional(),
    draft: z.boolean().default(false),
  }),
});

export const collections = { homepage, pages, journey, pillars };
