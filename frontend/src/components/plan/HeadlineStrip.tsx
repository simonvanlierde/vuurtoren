/** The persistent Plan headline: the FI date as the answer, with Coast-FIRE and the
 * crossover under it as evidence, then FIRE number · lens figure · savings rate. Only the
 * lens figure changes with the lens, and the Composition lens has none. */
import { useRef } from "react";
import type { ProjectionResponse } from "../../lib/api";
import { crossoverMonth, crossoverRows } from "../../lib/crossover";
import { useLocale, useT } from "../../lib/i18n";
import { formatEuros, formatPercent } from "../../lib/money";
import { EditedBadge } from "../ui/EditedBadge";

export interface HeadlineSlot {
  label: string;
  value: string;
}

export function formatMonth(
  iso: string | null | undefined,
  notReached: string,
  locale: "nl" | "en",
): string {
  if (!iso) return notReached;
  const intlLocale = locale === "nl" ? "nl-NL" : "en-US";
  // A date-only ISO string parses as UTC midnight, so format it in UTC too: in the
  // viewer's zone, west of UTC, it is the last day of the month before.
  return new Intl.DateTimeFormat(intlLocale, {
    year: "numeric",
    month: "long",
    timeZone: "UTC",
  }).format(new Date(iso));
}

export function UserEditsMarker() {
  const t = useT();
  return <EditedBadge>{t("plan.userEdits")}</EditedBadge>;
}

export function HeadlineStrip({
  projection,
  slot,
}: {
  projection: ProjectionResponse | undefined;
  slot: HeadlineSlot | null;
}) {
  const t = useT();
  const [locale] = useLocale();
  const fire = projection?.fire;
  const notReached = t("plan.notReached");
  // With no spending there is nothing to fund, so FI is undefined rather than missed:
  // "Not reached" in brick would call a household with no expenses a shortfall.
  const undefinedFi = fire !== undefined && fire.fire_number <= 0;
  const fiDate = !fire
    ? "—"
    : undefinedFi
      ? t("plan.headline.undefined")
      : formatMonth(fire.fi_dates[0], notReached, locale);
  // The bridge: when an assumption moves the FI date, keep the date it moved from on
  // screen. Without it, "December 2043" flips to "Not reached" with nothing connecting
  // the two — the moment of maximum anxiety and the strip said the least. Lags one
  // render behind, and is dropped while data is still loading so "—" is never a "was".
  const prevFi = useRef<string | null>(null);
  const lastFi = useRef<string | null>(null);
  const lastLocale = useRef(locale);
  if (lastLocale.current !== locale) {
    // A locale switch reformats the same date; that is not a move, so no bridge.
    lastLocale.current = locale;
    prevFi.current = null;
    lastFi.current = null;
  }
  if (fire && fiDate !== lastFi.current) {
    prevFi.current = lastFi.current;
    lastFi.current = fiDate;
  }
  const wasFi = prevFi.current;
  // The two earlier dates are evidence for the FI date, not rivals to it: Coast-FIRE is
  // when saving could stop, the crossover when returns first cover spending.
  const evidence =
    projection && fire && !undefinedFi
      ? [
          {
            label: t("plan.headline.coast"),
            value: formatMonth(fire.coast_fire_dates[0], notReached, locale),
          },
          {
            label: t("plan.crossover.tab"),
            value: formatMonth(crossoverMonth(crossoverRows(projection)), notReached, locale),
          },
        ]
      : [];
  const figures = [
    { label: t("plan.headline.fire"), value: fire ? formatEuros(fire.fire_number) : "—" },
    ...(slot ? [slot] : []),
    { label: t("plan.headline.savings"), value: fire ? formatPercent(fire.savings_rate) : "—" },
  ];
  return (
    // aria-live on the strip, not per-cell: a slider edit changes several figures in one
    // response, and one polite announcement of the row beats four interleaved ones.
    <div aria-live="polite" className="flex flex-col gap-4 sm:flex-row sm:items-start sm:gap-10">
      {/* The FI date is the answer the product exists to give: it leads, one step larger,
          with the dates that explain it underneath. */}
      <dl>
        <dt className="text-sm">{t("plan.headline.fi")}</dt>
        <dd className="font-display text-3xl tabular-nums">
          {/* Not reached is a state, not a date — it reads in brick (the Two Hues rule:
              debt and shortfall own that colour). */}
          <span
            className={fire?.fi_dates[0] === null && !undefinedFi ? "text-destructive" : undefined}
          >
            {fiDate}
          </span>
          {wasFi && (
            <span className="text-ink-navy/70 dark:text-paper/60 block text-xs font-sans">
              {t("plan.headline.was").replaceAll("{v}", wasFi)}
            </span>
          )}
        </dd>
        {undefinedFi && (
          <dd className="mt-1 max-w-xs text-sm text-ink-navy/70 dark:text-paper/70">
            {t("plan.headline.undefinedHint")}
          </dd>
        )}
        {evidence.length > 0 && (
          <dd className="mt-1">
            <dl className="flex flex-wrap gap-x-4 gap-y-1 text-sm">
              {evidence.map((e) => (
                <div key={e.label} className="flex gap-1.5">
                  <dt className="text-ink-navy/70 dark:text-paper/70">{e.label}</dt>
                  <dd className="tabular-nums">{e.value}</dd>
                </div>
              ))}
            </dl>
          </dd>
        )}
      </dl>
      <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3">
        {figures.map((f) => (
          <div key={f.label}>
            <dt className="text-sm">{f.label}</dt>
            <dd className="font-display text-2xl tabular-nums">{f.value}</dd>
          </div>
        ))}
      </dl>
    </div>
  );
}
