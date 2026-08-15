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
      Schrijven: ["posts"],
      "Vaste pagina's": ["pages"],
    },
  },
  collections: {
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
