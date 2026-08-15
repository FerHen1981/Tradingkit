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

export const collections = { posts, pages };
