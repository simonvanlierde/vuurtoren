/** The sensitivity tornado: move one assumption at a time, rank how far
 * the FIRE date travels.
 *
 * The point is the inverse of what it looks like. A wide bar says "this assumption is
 * worth arguing about"; a narrow one says "stop worrying about this", which is the more
 * useful and less often given answer — so the readout names the weakest input as
 * prominently as the strongest.
 *
 * Hand-drawn SVG, not Recharts, for the same reason `TimelineChart` is: Recharts renders
 * a range bar (`dataKey` holding a `[low, high]` tuple) as a full-width, zero-height
 * rectangle here, and a tornado is four rectangles and a rule — far less code than
 * fighting the library for it. Sized in a viewBox roughly 1:1 with CSS pixels so the
 * labels stay legible at 320px, the lesson from the mobile pass. */
import type { SensitivityResult, SensitivityRow } from "../../lib/api";
import { SERIES } from "../../lib/chartColors";
import { useT } from "../../lib/i18n";
import { formatEuroTick } from "../../lib/money";
import { linearScale } from "../../lib/timeline";
import { BELOW_SM, useMediaQuery } from "../../lib/useMediaQuery";

/** Amber for the widest bar, quiet navy for the rest: one focal point, not a rainbow. */
const WIDEST = SERIES.focus;
const REST = SERIES.neutral;

const ROW_H = 34;
const BAR_H = 16;

function span(row: SensitivityRow): number | null {
  return row.low === null || row.high === null ? null : Math.abs(row.high - row.low);
}

export function SensitivityPanel({ data }: { data: SensitivityResult | undefined }) {
  const t = useT();
  const narrow = useMediaQuery(BELOW_SM);
  const label = (knob: SensitivityRow["knob"]) =>
    t(`plan.sens.knob.${knob}` as Parameters<typeof t>[0]);

  if (!data || data.rows.length === 0) {
    return (
      <p className="p-4 text-sm text-ink-navy/70 dark:text-paper/60 sm:p-8">
        {t("plan.sens.empty")}
      </p>
    );
  }
  if (data.baseline === null) {
    return (
      <p className="p-4 text-sm text-ink-navy/70 dark:text-paper/60 sm:p-8">
        {t("plan.sens.noBaseline")}
      </p>
    );
  }

  const baseline = data.baseline;
  const isYears = data.metric === "fi_year";
  // Rows arrive sorted widest first. A knob that reaches "never" in one direction has no
  // finite bar and is named below the chart rather than drawn with an invented end.
  const finite = data.rows.filter((r) => span(r) !== null);
  const unbounded = data.rows.filter((r) => span(r) === null);

  if (finite.length === 0) {
    return (
      <p className="p-4 text-sm text-ink-navy/70 dark:text-paper/60 sm:p-8">
        {t("plan.sens.noBaseline")}
      </p>
    );
  }

  // Every knob tied at the smallest span, not just the row that sorted last.
  const narrowest = span(finite[finite.length - 1]);
  const weakest = finite.filter((r) => span(r) === narrowest).map((r) => r.knob);

  const bars = finite.map((r) => ({
    knob: r.knob,
    lo: Math.min(r.low as number, r.high as number) - baseline,
    hi: Math.max(r.low as number, r.high as number) - baseline,
  }));

  // At 320px there is no room for a label column beside the bars — "Safe withdrawal rate"
  // ran off the left edge as "e withdrawal rate" — so the label sits above its own bar and
  // the plot uses the full width.
  const W = narrow ? 300 : 640;
  const padLeft = narrow ? 4 : 150;
  // Room reserved to the right of the widest bar for its value label. Without it the
  // widest bar reaches the plot edge by construction and its label had nowhere to go.
  const valueRoom = 58;
  const padRight = 12 + valueRoom;
  const padBottom = 26;
  const rowH = narrow ? ROW_H + 16 : ROW_H;
  const H = bars.length * rowH + padBottom;

  // Symmetric around zero so the baseline sits mid-plot and a bar's side reads as its
  // direction, not as an artefact of the extent.
  const extent = Math.max(...bars.map((b) => Math.max(Math.abs(b.lo), Math.abs(b.hi))), 0.5);
  const x = linearScale(-extent, extent, padLeft, W - padRight);
  const zero = x(0);
  const fmtTick = (v: number) =>
    isYears ? `${v > 0 ? "+" : ""}${Math.round(v)}` : formatEuroTick(v);

  return (
    <section aria-labelledby="sens-heading" className="space-y-3 p-4 sm:p-8">
      <h2
        id="sens-heading"
        className="text-sm uppercase tracking-wide text-ink-navy/70 dark:text-paper/60"
      >
        {t("plan.sens.heading")}
      </h2>

      {/* Naming one knob as the weak one is a claim about the others too. At the FI-year
          metric the spans are whole years, so knobs routinely tie — return assumption and
          inflation both move this plan by 0 years — and singling out the last row read as
          a rendering bug beside two identical bars. Name everything tied at the bottom,
          and when that is everything, say so instead. */}
      <p className="max-w-prose text-sm">
        {weakest.length === finite.length
          ? t("plan.sens.sentenceTied").replace("{knobs}", weakest.map(label).join(", "))
          : t("plan.sens.sentence")
              .replace("{strong}", label(finite[0].knob))
              .replace("{weak}", weakest.map(label).join(" and "))}
      </p>

      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="w-full"
        role="img"
        aria-label={t("plan.sens.heading")}
        preserveAspectRatio="xMidYMid meet"
      >
        {bars.map((b, i) => {
          const y = i * rowH;
          const left = x(b.lo);
          const right = x(b.hi);
          return (
            <g key={b.knob}>
              <text
                x={narrow ? padLeft : padLeft - 8}
                y={narrow ? y + 12 : y + rowH / 2 + 4}
                textAnchor={narrow ? "start" : "end"}
                className="fill-ink-navy dark:fill-paper"
                fontSize="11"
              >
                {label(b.knob)}
              </text>
              <rect
                x={left}
                y={narrow ? y + 18 : y + (rowH - BAR_H) / 2}
                width={Math.max(right - left, 1)}
                height={BAR_H}
                rx="2"
                fill={i === 0 ? WIDEST : REST}
                fillOpacity={i === 0 ? 0.9 : 0.7}
              />
              {/* The numbers, not just the length. Two knobs can move the FI *year* by
                  the same whole number and then draw pixel-identical bars — return
                  assumption and inflation did — which reads as a rendering bug until
                  the values say otherwise. */}
              <text
                x={right + 6}
                y={(narrow ? y + 18 : y + (rowH - BAR_H) / 2) + BAR_H / 2 + 3.5}
                textAnchor="start"
                className="fill-ink-navy/70 dark:fill-paper/70"
                fontSize="10"
              >
                {fmtTick(b.lo)} … {fmtTick(b.hi)}
              </text>
            </g>
          );
        })}

        {/* The plan as it stands. Every bar is read against this, so it is drawn, not implied. */}
        <line
          x1={zero}
          x2={zero}
          y1={0}
          y2={H - padBottom}
          className="stroke-ink-navy/40 dark:stroke-paper/40"
        />
        {[-extent, 0, extent].map((v) => (
          <text
            key={v}
            x={x(v)}
            y={H - 8}
            textAnchor="middle"
            className="fill-ink-navy/60 dark:fill-paper/60"
            fontSize="10"
          >
            {fmtTick(v)}
          </text>
        ))}
      </svg>

      <p className="text-xs text-ink-navy/70 dark:text-paper/60">{t("plan.sens.axis")}</p>

      <p className="text-xs text-ink-navy/70 dark:text-paper/60">
        {t("plan.sens.deltaNote").replace(
          "{deltas}",
          data.rows
            .map((r) => `${label(r.knob)} ±${(r.delta * 100).toFixed(r.delta < 0.01 ? 1 : 0)}pp`)
            .join(" · "),
        )}
      </p>

      {unbounded.length > 0 && (
        <p className="text-xs text-brick">
          {t("plan.sens.never").replace("{knobs}", unbounded.map((r) => label(r.knob)).join(", "))}
        </p>
      )}
    </section>
  );
}
