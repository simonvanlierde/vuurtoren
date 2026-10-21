/** The persistent Plan headline strip: FIRE number · FI date ·
 * lens-reactive slot · savings rate. Only the third slot ever changes. */
import { useRef } from "react";
import type { ProjectionResponse } from "../../lib/api";
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
  fire,
  slot,
}: {
  fire: ProjectionResponse["fire"] | undefined;
  slot: HeadlineSlot;
}) {
  const t = useT();
  const [locale] = useLocale();
  const fiDate = fire ? formatMonth(fire.fi_dates[0], t("plan.notReached"), locale) : "—";
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
  return (
    // aria-live on the strip, not per-cell: a slider edit changes several figures in one
    // response, and one polite announcement of the row beats four interleaved ones.
    <dl aria-live="polite" className="grid grid-cols-2 gap-4 sm:grid-cols-4">
      {/* The FI date leads, one step larger: it is the answer the product exists to give.
          The other three figures are its supporting evidence and stay a size down. */}
      <div>
        <dt className="text-sm">{t("plan.headline.fi")}</dt>
        <dd className="font-display text-3xl tabular-nums">
          {/* Not reached is a state, not a date — it reads in brick (the Two Hues rule:
              debt and shortfall own that colour). */}
          <span className={fire && fire.fi_dates[0] === null ? "text-destructive" : undefined}>
            {fiDate}
          </span>
          {wasFi && (
            <span className="text-ink-navy/70 dark:text-paper/60 block text-xs font-sans">
              {t("plan.headline.was").replaceAll("{v}", wasFi)}
            </span>
          )}
        </dd>
      </div>
      <div>
        <dt className="text-sm">{t("plan.headline.fire")}</dt>
        <dd className="font-display text-2xl tabular-nums">
          {fire ? formatEuros(fire.fire_number) : "—"}
        </dd>
      </div>
      <div>
        <dt className="text-sm">{slot.label}</dt>
        <dd className="font-display text-2xl tabular-nums">{slot.value}</dd>
      </div>
      <div>
        <dt className="text-sm">{t("plan.headline.savings")}</dt>
        <dd className="font-display text-2xl tabular-nums">
          {fire ? formatPercent(fire.savings_rate) : "—"}
        </dd>
      </div>
    </dl>
  );
}
