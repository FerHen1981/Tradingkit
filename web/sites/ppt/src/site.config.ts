/**
 * Site identity for pipsandpalmtrees.com.
 * Same shape as sites/mex/src/site.config.ts — that is the contract the shared
 * brand components read against.
 */
export const site = {
  name: "Pips & Palm Trees",
  origin: process.env.SITE_URL ?? "https://www.pipsandpalmtrees.com",
  locale: "nl-NL",
  ogLocale: "nl_NL",
  favicon: "🌴",
  description:
    "Emigreren als daytrader, van binnenuit. Wat de verhuizing naar Curaçao echt kost aan tijd, papierwerk en aannames — plus de tips die ik zelf had willen hebben.",

  brand: {
    mark: "P&PT",
    word: "Pips & Palm Trees",
    tagline:
      "Notities van een daytrader die verhuisde. Eerlijk over het papierwerk.",
  },

  nav: [
    { label: "Start hier", href: "/start-hier" },
    { label: "Gidsen", href: "/gidsen" },
    { label: "Begrippen", href: "/begrippen" },
    { label: "Blog", href: "/blog" },
    { label: "Over mij", href: "/over" },
  ],

  cta: { label: "MEX Traders", href: "https://www.mex-traders.com" },

  footer: {
    columns: [
      {
        title: "Lezen",
        items: [
          { label: "Start hier", href: "/start-hier" },
          { label: "Gidsen", href: "/gidsen" },
          { label: "Alle posts", href: "/blog" },
          { label: "RSS", href: "/rss.xml" },
        ],
      },
      {
        title: "Naslag",
        items: [
          { label: "Begrippenlijst", href: "/begrippen" },
          { label: "Tips & tricks", href: "/tags/tips" },
          { label: "Emigratie", href: "/tags/emigratie" },
        ],
      },
      {
        title: "Over",
        items: [
          { label: "Over mij", href: "/over" },
          { label: "Contact", href: "/contact" },
        ],
      },
      {
        title: "Groep",
        items: [{ label: "MEX Traders", href: "https://www.mex-traders.com" }],
      },
    ],
    legal: [
      { label: "Privacy", href: "/juridisch/privacy" },
      { label: "Disclaimer", href: "/juridisch/disclaimer" },
    ],
  },

  entity: "Pips & Palm Trees · een uitgave van MEX Traders N.V., Curaçao",
  registration: "",

  /**
   * The editorial site needs its own disclaimer. The corporate default talks
   * about proprietary trading; here the risk is different — a personal blog
   * about emigrating and trading can read as advice if nobody says otherwise.
   */
  disclaimer:
    "Dit is een persoonlijk weblog. Wat hier staat zijn eigen ervaringen en meningen, geen beleggings-, fiscaal, juridisch of emigratieadvies, en geen aanbod van welke dienst dan ook. Regels rond belastingen, verblijf en handelen verschillen per persoon en veranderen; laat u adviseren over uw eigen situatie voordat u iets besluit. Handelen in futures en valuta brengt aanzienlijk risico op verlies met zich mee.",

  contact: {
    email: "hallo@pipsandpalmtrees.com",
  },
} as const;

export type SiteConfig = typeof site;
