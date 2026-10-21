/**
 * Money arrives from the API as Decimal-serialised strings with exactly two decimal
 * places (spec's `Money` type, always quantized to cents). Parsing through a string
 * -> integer-cents path (rather than `parseFloat`) means summing a household's worth
 * of accounts never drifts the way repeated float addition would.
 *
 * NOTE: integer cents fits comfortably in a JS number up to ~90 trillion EUR
 * (2^53 / 100) — a BigInt cents type would be needed only past that ceiling.
 */

const EUR_FORMAT = new Intl.NumberFormat("nl-NL", { style: "currency", currency: "EUR" });
const PERCENT_FORMAT = new Intl.NumberFormat("nl-NL", {
  style: "percent",
  minimumFractionDigits: 1,
  maximumFractionDigits: 1,
});

/** Parse a `"12345.67"` / `"-50000.00"` Decimal string into whole eurocents. */
export function toCents(value: string): number {
  const negative = value.startsWith("-");
  const abs = negative ? value.slice(1) : value;
  const [whole, frac = ""] = abs.split(".");
  const cents = Number(whole || "0") * 100 + Number(frac.padEnd(2, "0").slice(0, 2) || "0");
  return negative ? -cents : cents;
}

export function formatCents(cents: number): string {
  return EUR_FORMAT.format(cents / 100);
}

export function formatMoney(value: string): string {
  return formatCents(toCents(value));
}

/** `part / whole` as a percentage string, or an em dash when `whole` is zero. */
export function formatShare(part: number, whole: number): string {
  if (whole === 0) return "—";
  return PERCENT_FORMAT.format(part / whole);
}

/** A ratio (e.g. `fire.savings_rate`) as a percentage string — no part/whole division. */
export function formatPercent(ratio: number): string {
  return PERCENT_FORMAT.format(ratio);
}

const EUR_WHOLE_FORMAT = new Intl.NumberFormat("nl-NL", {
  style: "currency",
  currency: "EUR",
  maximumFractionDigits: 0,
});

/**
 * The projection engine's numbers (net worth, FIRE number, chart components) are plain
 * euro floats, not `Money`-as-string (the engine is float64 numpy throughout).
 * Format directly — no cents round-trip, since there is no Decimal string to parse.
 *
 * **No cents, deliberately, and this is the line between the two.** A projected
 * `€ 4.776.654,70` for 2085 claims a precision the model does not have; a *stored*
 * balance really is exact to the cent, so `formatCents`/`formatMoney` keep theirs. The
 * engine stays exact either way — this is display only.
 */
export function formatEuros(value: number): string {
  return EUR_WHOLE_FORMAT.format(value);
}

const EUR_TICK_FORMAT = new Intl.NumberFormat("nl-NL", {
  style: "currency",
  currency: "EUR",
  notation: "compact",
  maximumFractionDigits: 1,
});

/** Chart axis labels: "€ 6 mln." instead of "€ 6.000.000,00", which overflows the
 * axis gutter and renders with the leading digits cut off. */
export function formatEuroTick(value: number): string {
  return EUR_TICK_FORMAT.format(value);
}

/** The numeric box beside each assumption slider: a ratio (`0.035`) is shown and typed
 * in percentage points ("3,5"). `type="number"` is no good here — it discards the comma
 * an nl keyboard produces — so the pair below does the conversion by hand. */
export function percentInputText(ratio: number): string {
  // Two decimals of a percentage point: the sliders step in tenths, but a shared link's
  // hash can carry finer, and the box must not show a rounder number than the plan uses.
  return String(Math.round(ratio * 10000) / 100).replace(".", ",");
}

/** `null` for anything that isn't a number yet, so a half-typed or cleared box leaves
 * the slider where it was instead of jumping to zero. */
export function parsePercentInput(text: string): number | null {
  if (text.trim() === "") return null;
  const n = Number(text.replace(",", "."));
  return Number.isFinite(n) ? n / 100 : null;
}

/** Shape check for a user-typed Decimal string (client validates shape only). */
export function isDecimalString(s: string): boolean {
  return /^-?\d+(\.\d+)?$/.test(s.trim());
}
