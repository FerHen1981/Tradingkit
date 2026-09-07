// @ts-check
import { defineConfig } from "astro/config";
import mdx from "@astrojs/mdx";
import sitemap from "@astrojs/sitemap";
import react from "@astrojs/react";
import keystatic from "@keystatic/astro";
import cloudflare from "@astrojs/cloudflare";

const SITE = process.env.SITE_URL ?? "https://www.mex-traders.com";

/**
 * The CMS admin needs server routes; the public site does not. Keeping those
 * two facts apart is what lets the production site deploy as plain files.
 *
 *   npm run dev                     → editor at /keystatic against your working
 *                                     copy; nothing is deployed.
 *   npm run build                   → fully static output. No admin, no server,
 *                                     no adapter. This is the default deploy.
 *   KEYSTATIC_MODE=github npm run build
 *                                   → admin ships with the site so you can edit
 *                                     from a browser or phone. Needs the
 *                                     Cloudflare adapter, which is why it is a
 *                                     separate mode rather than the default.
 */
const CMS_CLOUD = process.env.KEYSTATIC_MODE === "github";
const IS_DEV = process.argv.includes("dev");

const integrations = [
  mdx(),
  sitemap({ filter: (page) => !page.includes("/keystatic") }),
];

if (IS_DEV || CMS_CLOUD) {
  integrations.push(react(), keystatic());
}

export default defineConfig({
  site: SITE,
  trailingSlash: "never",
  integrations,
  build: { format: "file" },
  markdown: {
    shikiConfig: {
      themes: { light: "github-light", dark: "github-dark-dimmed" },
      wrap: true,
    },
  },
  ...(CMS_CLOUD ? { adapter: cloudflare(), output: "server" } : {}),
});
