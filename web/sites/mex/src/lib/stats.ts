import {
  formatCount,
  formatPercent,
  formatR,
  formatRatio,
  formatSlippage,
} from "@mex/brand/units";

/**
 * Turns the published snapshot into display tiles.
 *
 * Metrics the snapshot cannot yet derive arrive as null and are dropped rather
 * than rendered as an em dash — a public page reading "PF —" invites the wrong
 * question. When the reconciliation job starts emitting them the tiles appear
 * on their own.
 */

export interface PublicStats {
  sample?: boolean;
  generated_at: string;
  period: { from: string; to: string };
  delay: string;
  headline: {
    trades: number | null;
    win_rate: number | null;
    profit_factor: number | null;
    r_total: number | null;
    expectancy_r: number | null;
    months_live: number | null;
    avg_slippage_ticks: number | null;
  };
  markets: {
    symbol: string;
    label: string;
    unit: string;
    net_units: number;
    trades: number;
    win_rate: number;
    r_total: number | null;
    profit_factor: number | null;
    slippage_ticks?: number | null;
    status?: string;
  }[];
  equity: { t: string; v: number }[];
}

type Tile = {
  label: string;
  value: string;
  note?: string;
  tone?: "" | "pos" | "neg" | "accent" | "accent-2";
  hero?: boolean;
};

const has = (v: number | null | undefined): v is number =>
  v !== null && v !== undefined && !Number.isNaN(v);

export function headlineTiles(stats: PublicStats): Tile[] {
  const h = stats.headline;
  const tiles: Tile[] = [];

  if (has(h.r_total)) {
    tiles.push({
      label: "Netto resultaat",
      value: formatR(h.r_total),
      note: "in R — risico-genormaliseerd",
      tone: h.r_total >= 0 ? "pos" : "neg",
      hero: true,
    });
  }

  if (has(h.trades)) {
    tiles.push({
      label: "Trades",
      value: formatCount(h.trades),
      note: "gereconcilieerd",
    });
  }

  if (has(h.win_rate)) {
    tiles.push({
      label: "Win-rate",
      value: formatPercent(h.win_rate),
      note: "winst wordt gemaakt op grootte, niet op frequentie",
    });
  }

  if (has(h.profit_factor)) {
    tiles.push({
      label: "Profit factor",
      value: formatRatio(h.profit_factor),
      note: "bruto winst / bruto verlies",
      tone: "accent",
    });
  }

  if (has(h.avg_slippage_ticks)) {
    tiles.push({
      label: "Gem. slippage",
      value: formatSlippage(h.avg_slippage_ticks),
      note: "intentie versus werkelijke fill",
      tone: "accent-2",
    });
  }

  if (has(h.months_live)) {
    tiles.push({
      label: "Live",
      value: `${formatCount(h.months_live)} mnd`,
      note: `${stats.period.from} — ${stats.period.to}`,
    });
  }

  return tiles;
}

/** The provenance line under a stats block. Never omit it. */
export function statsSource(stats: PublicStats): string {
  const generated = new Date(stats.generated_at);
  const stamp = Number.isNaN(generated.getTime())
    ? "onbekend"
    : generated.toLocaleString("nl-NL", {
        day: "numeric",
        month: "short",
        year: "numeric",
        hour: "2-digit",
        minute: "2-digit",
      });

  return [
    `Bron: gereconcilieerd handelsjournaal · vertraging ${stats.delay} · bijgewerkt ${stamp}.`,
    "Alle waarden in units (ticks en R). Bedragen, rekeningnummers en handelspartijen worden niet gepubliceerd.",
    "Historische resultaten van eigen handelsrekeningen; geen indicatie voor toekomstige resultaten.",
  ].join(" ");
}
