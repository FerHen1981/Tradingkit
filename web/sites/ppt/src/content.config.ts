import { defineCollection, z } from "astro:content";
import { glob } from "astro/loaders";

/** Mirrors keystatic.config.ts. Change a field in one, change it in both. */

const posts = defineCollection({
  loader: glob({ pattern: "**/*.mdx", base: "./src/content/posts" }),
  schema: z.object({
    title: z.string(),
    summary: z.string(),
    date: z.coerce.date(),
    updated: z.coerce.date().optional(),
    tags: z.array(z.string()).default([]),
    /** Groups a multi-part story, e.g. "Verhuizen naar Curaçao". */
    series: z.string().optional(),
    cover: z.string().optional(),
    /** YouTube id — turns the post into a vlog entry with a facade embed. */
    video: z.string().optional(),
    featured: z.boolean().default(false),
    draft: z.boolean().default(false),
  }),
});

const pages = defineCollection({
  loader: glob({ pattern: "**/*.mdx", base: "./src/content/pages" }),
  schema: z.object({
    title: z.string(),
    description: z.string(),
    eyebrow: z.string().optional(),
    lead: z.string().optional(),
    draft: z.boolean().default(false),
    noindex: z.boolean().default(false),
  }),
});

/**
 * De begrippenlijst.
 *
 * `sources` verwijst naar id's in src/data/sources.json. Een begrip dat een
 * feitelijke claim doet hoort een bron te hebben; `authority` maakt expliciet
 * of die bron een toezichthouder, beurs of wetgever is, of dat het begrip
 * alleen in de praktijk zo wordt gebruikt. Dat onderscheid is voor de lezer
 * belangrijker dan de definitie zelf.
 */
const glossary = defineCollection({
  loader: glob({ pattern: "**/*.mdx", base: "./src/content/glossary" }),
  schema: z.object({
    term: z.string(),
    /** Synoniemen en Engelse varianten — voor zoeken en voor "zie ook". */
    aliases: z.array(z.string()).default([]),
    category: z.enum([
      "futures",
      "handel",
      "risico",
      "propfirms",
      "regels",
      "emigratie",
    ]),
    /** Eén zin. Dit is wat in het overzicht en in de zoekresultaten staat. */
    short: z.string(),
    /** True wanneer de definitie op een toezichthouder, beurs of wet steunt. */
    authority: z.boolean().default(false),
    sources: z.array(z.string()).default([]),
    related: z.array(z.string()).default([]),
    updated: z.coerce.date().optional(),
    draft: z.boolean().default(false),
  }),
});

/** Evergreen gidsen — de kennisbank, los van de chronologische blog. */
const guides = defineCollection({
  loader: glob({ pattern: "**/*.mdx", base: "./src/content/guides" }),
  schema: z.object({
    title: z.string(),
    summary: z.string(),
    /** Bepaalt de volgorde binnen het leerpad. */
    order: z.number().default(100),
    level: z.enum(["start", "verdieping", "gevorderd"]).default("start"),
    topic: z.enum(["emigratie", "trading", "bedrijf", "geld"]),
    updated: z.coerce.date(),
    /** Wat de lezer na afloop kan of weet. */
    takeaways: z.array(z.string()).default([]),
    sources: z.array(z.string()).default([]),
    draft: z.boolean().default(false),
  }),
});

export const collections = { posts, pages, glossary, guides };
