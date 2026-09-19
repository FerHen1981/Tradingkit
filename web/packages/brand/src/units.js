/**
 * Unit formatting for every public and viewer-facing surface.
 *
 * Deliberately there is NO dollar formatter in this file. The public sites and
 * the viewer role must be structurally incapable of rendering currency: the
 * snapshot they consume never carries a dollar field, and this module gives
 * them no way to print one. Currency formatting lives only in the portal's
 * owner/partner path, server-side.
 *
 * Conversion from money to units happens once, in Python
 * (portal/app/units.py), against the contract registry. This module only
 * formats values that already arrived as units.
 */

/** Display metadata per contract. Mirrors backtest CONTRACTS + docs/instruments.md. */
export const CONTRACTS = {
  NQ: { label: "Nasdaq 100", unit: "ticks", tick: 0.25, perPoint: 20 },
  ES: { label: "S&P 500", unit: "ticks", tick: 0.25, perPoint: 50 },
  YM: { label: "Dow 30", unit: "ticks", tick: 1.0, perPoint: 5 },
  RTY: { label: "Russell 2000", unit: "ticks", tick: 0.1, perPoint: 50 },
  GC: { label: "Goud", unit: "ticks", tick: 0.1, perPoint: 100 },
  MGC: { label: "Goud (micro)", unit: "ticks", tick: 0.1, perPoint: 10 },
  CL: { label: "Ruwe olie", unit: "ticks", tick: 0.01, perPoint: 1000 },
  SI: { label: "Zilver", unit: "ticks", tick: 0.005, perPoint: 5000 },
  FX: { label: "Spot FX", unit: "pips", tick: null, perPoint: null },
};

const nf = (locale, opts) => new Intl.NumberFormat(locale, opts);

/**
 * Signed integer-ish unit count: "+6.011 ticks", "−655 ticks".
 * Uses a real minus sign (U+2212) so columns align in tabular-nums.
 */
export function formatUnits(value, unit = "ticks", locale = "nl-NL") {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  const body = nf(locale, { maximumFractionDigits: 0 }).format(Math.abs(value));
  return `${sign}${body}${unit ? ` ${unit}` : ""}`;
}

/**
 * R-multiple — the only unit that is meaningful when summed across
 * instruments, because it is already normalised by each trade's own risk.
 */
export function formatR(value, locale = "nl-NL", digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  const sign = value > 0 ? "+" : value < 0 ? "−" : "";
  const body = nf(locale, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(Math.abs(value));
  return `${sign}${body}R`;
}

export function formatPercent(value, locale = "nl-NL", digits = 1) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return `${nf(locale, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value)}%`;
}

export function formatRatio(value, locale = "nl-NL", digits = 2) {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return nf(locale, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  }).format(value);
}

export function formatCount(value, locale = "nl-NL") {
  if (value === null || value === undefined || Number.isNaN(value)) return "—";
  return nf(locale, { maximumFractionDigits: 0 }).format(value);
}

/** Slippage is the house metric: small numbers, signed, two decimals. */
export function formatSlippage(ticks, locale = "nl-NL") {
  if (ticks === null || ticks === undefined || Number.isNaN(ticks)) return "—";
  const sign = ticks > 0 ? "+" : ticks < 0 ? "−" : "";
  return `${sign}${nf(locale, {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(Math.abs(ticks))} ticks`;
}

export function formatDate(value, locale = "nl-NL") {
  if (!value) return "—";
  const d = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleDateString(locale, {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

/** Direction of a value for colour semantics; never guesses on zero. */
export function tone(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "";
  if (value > 0) return "pos";
  if (value < 0) return "neg";
  return "";
}
