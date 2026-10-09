// @ts-check
import { defineConfig } from "astro/config";
import mdx from "@astrojs/mdx";
import sitemap from "@astrojs/sitemap";
import react from "@astrojs/react";
import keystatic from "@keystatic/astro";
import cloudflare from "@astrojs/cloudflare";

const SITE = process.env.SITE_URL ?? "https://www.pipsandpalmtrees.com";

/** Same build modes as the corporate site — see sites/mex/astro.config.mjs. */
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
