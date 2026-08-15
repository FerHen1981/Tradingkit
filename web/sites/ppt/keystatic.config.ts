import { config, collection, fields } from "@keystatic/core";

/**
 * The editing surface for the blog. This is the one that gets used weekly, so
 * it is kept deliberately short: a post is a title, a summary, a date, some
 * tags and a body. Everything else is optional and stays out of the way.
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
    brand: { name: "Pips & Palm Trees" },
    navigation: {
      Schrijven: ["posts", "guides"],
      Naslag: ["glossary"],
      "Vaste pagina's": ["pages"],
    },
  },
  collections: {
    glossary: collection({
      label: "Begrippen",
      slugField: "term",
      path: "src/content/glossary/*",
      format: { contentField: "content" },
      columns: ["term", "category"],
      schema: {
        term: fields.slug({
          name: { label: "Begrip", validation: { isRequired: true } },
          slug: {
            label: "URL",
            description: "Wijzig dit niet meer nadat het begrip gedeeld is.",
          },
        }),
        short: fields.text({
          label: "Korte definitie",
          description:
            "Eén zin. Dit staat in het overzicht en in de zoekresultaten.",
          multiline: true,
          validation: { isRequired: true, length: { max: 300 } },
        }),
        category: fields.select({
          label: "Categorie",
          options: [
            { label: "Futures & contracten", value: "futures" },
            { label: "Handel & uitvoering", value: "handel" },
            { label: "Risico & statistiek", value: "risico" },
            { label: "Prop firms", value: "propfirms" },
            { label: "Regelgeving & toezicht", value: "regels" },
            { label: "Emigratie & fiscaal", value: "emigratie" },
          ],
          defaultValue: "handel",
        }),
        aliases: fields.array(fields.text({ label: "Synoniem" }), {
          label: "Synoniemen",
          description:
            "Engelse varianten en andere schrijfwijzen. Worden meegenomen in het zoeken.",
          itemLabel: (props) => props.value,
        }),
        authority: fields.checkbox({
          label: "Steunt op een officiële bron",
          description:
            "Aanvinken wanneer de definitie op een toezichthouder, beurs of wet steunt — niet wanneer het alleen praktijkgebruik is.",
          defaultValue: false,
        }),
        sources: fields.array(fields.text({ label: "Bron-id" }), {
          label: "Bronnen",
          description:
            "Id's uit src/data/sources.json, bijvoorbeeld cftc-glossary.",
          itemLabel: (props) => props.value,
        }),
        related: fields.array(fields.text({ label: "Slug" }), {
          label: "Zie ook",
          description: "Slugs van verwante begrippen.",
          itemLabel: (props) => props.value,
        }),
        updated: fields.date({ label: "Bijgewerkt op" }),
        draft: fields.checkbox({ label: "Concept", defaultValue: false }),
        content: fields.mdx({
          label: "Toelichting",
          options: {
            image: {
              directory: "public/media/begrippen",
              publicPath: "/media/begrippen/",
            },
          },
        }),
      },
    }),

    guides: collection({
      label: "Gidsen",
      slugField: "title",
      path: "src/content/guides/*",
      format: { contentField: "content" },
      columns: ["title", "topic"],
      entryLayout: "content",
      schema: {
        title: fields.slug({
          name: { label: "Titel", validation: { isRequired: true } },
        }),
        summary: fields.text({
          label: "Samenvatting",
          multiline: true,
          validation: { isRequired: true, length: { max: 300 } },
        }),
        topic: fields.select({
          label: "Onderwerp",
          options: [
            { label: "Emigratie", value: "emigratie" },
            { label: "Trading", value: "trading" },
            { label: "Bedrijf & structuur", value: "bedrijf" },
            { label: "Geld & administratie", value: "geld" },
          ],
          defaultValue: "emigratie",
        }),
        level: fields.select({
          label: "Niveau",
          options: [
            { label: "Start hier", value: "start" },
            { label: "Verdieping", value: "verdieping" },
            { label: "Gevorderd", value: "gevorderd" },
          ],
          defaultValue: "start",
        }),
        order: fields.integer({
          label: "Volgorde",
          description: "Lager komt eerder in het leerpad.",
          defaultValue: 100,
        }),
        updated: fields.date({
          label: "Bijgewerkt op",
          defaultValue: { kind: "today" },
          validation: { isRequired: true },
        }),
        takeaways: fields.array(fields.text({ label: "Punt" }), {
          label: "Wat je hierna weet",
          itemLabel: (props) => props.value,
        }),
        sources: fields.array(fields.text({ label: "Bron-id" }), {
          label: "Bronnen",
          itemLabel: (props) => props.value,
        }),
        draft: fields.checkbox({ label: "Concept", defaultValue: false }),
        content: fields.mdx({
          label: "Inhoud",
          options: {
            image: {
              directory: "public/media/gidsen",
              publicPath: "/media/gidsen/",
            },
          },
        }),
      },
    }),

    posts: collection({
      label: "Posts",
      slugField: "title",
      path: "src/content/posts/*",
      format: { contentField: "content" },
      columns: ["title", "date"],
      entryLayout: "content",
      schema: {
        title: fields.slug({
          name: { label: "Titel", validation: { isRequired: true } },
          slug: {
            label: "URL",
            description:
              "Het pad na /blog/. Wijzig dit niet meer nadat de post gedeeld is.",
          },
        }),
        summary: fields.text({
          label: "Samenvatting",
          description:
            "Twee zinnen. Dit staat in het overzicht, in de RSS-feed en op social media.",
          multiline: true,
          validation: { isRequired: true, length: { max: 300 } },
        }),
        date: fields.date({
          label: "Publicatiedatum",
          defaultValue: { kind: "today" },
          validation: { isRequired: true },
        }),
        updated: fields.date({
          label: "Bijgewerkt op",
          description: "Alleen invullen bij een inhoudelijke herziening.",
        }),
        tags: fields.array(
          fields.text({ label: "Tag" }),
          {
            label: "Tags",
            description: "Kleine letters, geen spaties. Bijv. emigratie, tips.",
            itemLabel: (props) => props.value,
          }
        ),
        series: fields.text({
          label: "Serie",
          description: "Optioneel. Groepeert een meerdelig verhaal.",
        }),
        cover: fields.image({
          label: "Uitgelichte afbeelding",
          directory: "public/media/posts",
          publicPath: "/media/posts/",
        }),
        video: fields.text({
          label: "YouTube-id",
          description:
            "Alleen het id uit de URL (na v=). Maakt er een vlog-post van.",
        }),
        featured: fields.checkbox({
          label: "Uitgelicht",
          description: "Zet deze post bovenaan de homepage.",
          defaultValue: false,
        }),
        draft: fields.checkbox({
          label: "Concept",
          description: "Concepten verschijnen niet op de live site.",
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
              directory: "public/media/posts",
              publicPath: "/media/posts/",
            },
          },
        }),
      },
    }),

    pages: collection({
      label: "Pagina's",
      slugField: "title",
      path: "src/content/pages/*",
      format: { contentField: "content" },
      schema: {
        title: fields.slug({
          name: { label: "Titel", validation: { isRequired: true } },
        }),
        description: fields.text({
          label: "Meta-omschrijving",
          multiline: true,
          validation: { isRequired: true, length: { max: 200 } },
        }),
        eyebrow: fields.text({ label: "Eyebrow" }),
        lead: fields.text({ label: "Introductie", multiline: true }),
        draft: fields.checkbox({ label: "Concept", defaultValue: false }),
        noindex: fields.checkbox({
          label: "Uitsluiten van zoekmachines",
          defaultValue: false,
        }),
        content: fields.mdx({
          label: "Inhoud",
          options: {
            image: {
              directory: "public/media/pages",
              publicPath: "/media/pages/",
            },
          },
        }),
      },
    }),
  },
});
