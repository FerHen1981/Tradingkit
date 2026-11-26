import { config, collection, singleton, fields } from "@keystatic/core";

/**
 * The admin UI at /keystatic. This is the "WordPress" half of the framework:
 * every field below becomes a form control, and saving writes a plain .mdx
 * file into src/content — which a commit deploys.
 *
 * Storage is local by default: `npm run dev` gives you the editor against your
 * working copy. Switch to GitHub storage (env KEYSTATIC_MODE=github) to edit
 * the live site from a browser or phone; that mode needs the server routes, so
 * the build then requires an adapter. See web/README.md.
 */
const storage =
  process.env.KEYSTATIC_MODE === "github"
    ? ({
        kind: "github",
        repo: { owner: "FerHen1981", name: "Tradingkit" },
      } as const)
    : ({ kind: "local" } as const);

export default config({
  storage,
  ui: {
    brand: { name: "MEX Traders" },
    navigation: {
      Inhoud: ["pages", "pillars", "journey"],
      Instellingen: ["homepage"],
    },
  },
  singletons: {
    homepage: singleton({
      label: "Homepage",
      path: "src/content/homepage",
      format: { contentField: "body" },
      schema: {
        eyebrow: fields.text({
          label: "Eyebrow",
          description: "Klein label boven de titel.",
          validation: { length: { max: 40 } },
        }),
        headline: fields.text({
          label: "Kop",
          multiline: true,
          validation: { isRequired: true },
        }),
        lead: fields.text({
          label: "Introductie",
          multiline: true,
          validation: { isRequired: true },
        }),
        primaryCta: fields.object({
          label: fields.text({ label: "Tekst" }),
          href: fields.text({ label: "Link" }),
        }, { label: "Primaire knop" }),
        secondaryCta: fields.object({
          label: fields.text({ label: "Tekst" }),
          href: fields.text({ label: "Link" }),
        }, { label: "Secundaire knop" }),
        statsIntro: fields.text({
          label: "Introductie bij de cijfers",
          multiline: true,
        }),
        body: fields.mdx({
          label: "Vrije tekst onderaan",
          options: {
            image: {
              directory: "public/media/home",
              publicPath: "/media/home/",
            },
          },
        }),
      },
    }),
  },
  collections: {
    pages: collection({
      label: "Pagina's",
      slugField: "title",
      path: "src/content/pages/*",
      format: { contentField: "content" },
      columns: ["title", "order"],
      schema: {
        title: fields.slug({
          name: {
            label: "Titel",
            validation: { isRequired: true },
          },
          slug: {
            label: "URL",
            description: "Het pad na het domein. Wijzig dit niet na publicatie.",
          },
        }),
        description: fields.text({
          label: "Meta-omschrijving",
          description: "Wat Google en social media tonen. Circa 150 tekens.",
          multiline: true,
          validation: { isRequired: true, length: { max: 200 } },
        }),
        eyebrow: fields.text({ label: "Eyebrow" }),
        lead: fields.text({ label: "Introductie", multiline: true }),
        order: fields.integer({ label: "Volgorde", defaultValue: 100 }),
        draft: fields.checkbox({
          label: "Concept",
          description: "Concepten verschijnen niet op de live site.",
          defaultValue: false,
        }),
        noindex: fields.checkbox({
          label: "Uitsluiten van zoekmachines",
          defaultValue: false,
        }),
        content: fields.mdx({
          label: "Inhoud",
          options: {
            // Without this, an image dropped into the editor is written next to
            // the .mdx file in src/content — where the static build never serves
            // it. Pointing at public/ makes an upload land somewhere the site
            // can actually reach.
            image: {
              directory: "public/media/pages",
              publicPath: "/media/pages/",
            },
          },
        }),
      },
    }),

    pillars: collection({
      label: "Wat we doen",
      slugField: "title",
      path: "src/content/pillars/*",
      format: { contentField: "content" },
      columns: ["title", "order"],
      schema: {
        title: fields.slug({ name: { label: "Titel", validation: { isRequired: true } } }),
        summary: fields.text({
          label: "Samenvatting",
          multiline: true,
          validation: { isRequired: true, length: { max: 240 } },
        }),
        mark: fields.text({ label: "Markering", description: "Kort teken of emoji." }),
        order: fields.integer({ label: "Volgorde", defaultValue: 100 }),
        draft: fields.checkbox({ label: "Concept", defaultValue: false }),
        content: fields.mdx({
          label: "Toelichting",
          options: {
            // Without this, an image dropped into the editor is written next to
            // the .mdx file in src/content — where the static build never serves
            // it. Pointing at public/ makes an upload land somewhere the site
            // can actually reach.
            image: {
              directory: "public/media/pillars",
              publicPath: "/media/pillars/",
            },
          },
        }),
      },
    }),

    journey: collection({
      label: "Curaçao — tijdlijn",
      slugField: "title",
      path: "src/content/journey/*",
      format: { contentField: "content" },
      columns: ["title", "date"],
      schema: {
        title: fields.slug({ name: { label: "Titel", validation: { isRequired: true } } }),
        date: fields.date({
          label: "Datum",
          validation: { isRequired: true },
        }),
        summary: fields.text({
          label: "Samenvatting",
          multiline: true,
          validation: { isRequired: true },
        }),
        phase: fields.text({ label: "Fase", description: "Bijv. 'Fase 1'." }),
        status: fields.select({
          label: "Status",
          options: [
            { label: "Afgerond", value: "done" },
            { label: "Loopt", value: "running" },
            { label: "Gepland", value: "planned" },
          ],
          defaultValue: "done",
        }),
        draft: fields.checkbox({ label: "Concept", defaultValue: false }),
        content: fields.mdx({
          label: "Toelichting",
          options: {
            image: {
              directory: "public/media/journey",
              publicPath: "/media/journey/",
            },
          },
        }),
      },
    }),
  },
});
