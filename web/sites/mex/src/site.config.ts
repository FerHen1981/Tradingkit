/**
 * Site identity for mex-traders.com.
 *
 * Everything a shared brand component needs to render this particular site
 * lives here, so the components in @mex/brand stay site-neutral and the second
 * site is a copy of this file with different values — not a fork of the code.
 */
export const site = {
  name: "MEX Traders",
  origin: process.env.SITE_URL ?? "https://www.mex-traders.com",
  locale: "nl-NL",
  ogLocale: "nl_NL",
  favicon: "◆",
  description:
    "MEX Traders is een proprietary trading company op Curaçao. Wij handelen systematisch met eigen kapitaal in futures — en meten elke uitvoering in ticks.",

  brand: {
    mark: "MEX",
    word: "Traders",
    tag: "Curaçao",
    tagline:
      "Systematisch handelen met eigen kapitaal. Gemeten in ticks, niet in beloftes.",
  },

  nav: [
    { label: "Wat we doen", href: "/wat-we-doen" },
    { label: "Methodiek", href: "/methodiek" },
    { label: "Resultaten", href: "/resultaten" },
    { label: "Curaçao", href: "/curacao" },
    { label: "Over ons", href: "/over" },
  ],

  /** De live cockpit (mex-viewer) draait op een eigen subdomein en eigen server. */
  cta: { label: "Inloggen", href: "https://app.mex-traders.com" },

  footer: {
    columns: [
      {
        title: "Bedrijf",
        items: [
          { label: "Wat we doen", href: "/wat-we-doen" },
          { label: "Over ons", href: "/over" },
          { label: "Curaçao", href: "/curacao" },
          { label: "Contact", href: "/contact" },
        ],
      },
      {
        title: "Inzicht",
        items: [
          { label: "Methodiek", href: "/methodiek" },
          { label: "Resultaten", href: "/resultaten" },
          { label: "Dashboard", href: "https://app.mex-traders.com" },
        ],
      },
      {
        title: "Groep",
        items: [
          { label: "Pips & Palm Trees", href: "https://www.pipsandpalmtrees.com" },
        ],
      },
    ],
    legal: [
      { label: "Privacy", href: "/juridisch/privacy" },
      { label: "Voorwaarden", href: "/juridisch/voorwaarden" },
      { label: "Disclaimer", href: "/juridisch/disclaimer" },
    ],
  },

  /**
   * Legal identity. Fill in the real registration number once the Curaçao
   * incorporation is final — an entity line without a number is fine, a wrong
   * number is not.
   */
  entity: "MEX Traders N.V. · Willemstad, Curaçao",
  registration: "",

  contact: {
    email: "info@mex-traders.com",
  },
} as const;

export type SiteConfig = typeof site;
