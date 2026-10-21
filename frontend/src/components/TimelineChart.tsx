// biome-ignore-all lint/a11y/useSemanticElements: this file is one hand-drawn SVG, and the SVG content model has no <button> — role + tabIndex is the only way to make a marker operable.
import { type KeyboardEvent, type PointerEvent, useId, useState } from "react";
import { BEAM, SERIES } from "../lib/chartColors";
import { useT } from "../lib/i18n";
import { formatEuroTick } from "../lib/money";
import {
  buildBandPath,
  buildLinePath,
  linearScale,
  niceTicks,
  type TimelineTick,
  type XY,
} from "../lib/timeline";
import { BELOW_SM, useMediaQuery } from "../lib/useMediaQuery";

/**
 * The timeline, hand-drawn as one SVG — NOT Recharts. Back to
 * front: THE BEAM (the p10–p90 Monte-Carlo cone in beacon amber, opening from a
 * single bright point at today), the net-worth curve coloured by component, then
 * the milestone markers. The beam draws once on load; `prefers-reduced-motion`
 * renders it statically. Beacon amber (#FFB020) is the beam's alone.
 */

export interface TimelineMarker {
  id: number;
  label: string;
  monthIndex: number;
  type: string;
}

export type { TimelineTick };

interface Props {
  months: string[];
  netWorth: number[];
  components: Record<string, number[]>;
  /** THE BEAM. Optional, and omitted on the Composition lens: p90 reached €5.0M there
   * against a €1.3M stack, so the cone drove the y domain and left home equity and
   * pension with no height at all. The Uncertainty lens is where it is the subject. */
  band?: { p10: number[]; p50: number[]; p90: number[] } | null;
  /** The Monte Carlo median, drawn as a dashed line over a fixed-return net-worth curve
   * so the two answers sit on one chart instead of the caption contradicting it. */
  median?: number[];
  markers: TimelineMarker[];
  ticks: TimelineTick[];
  selectedId: number | null;
  onSelect: (id: number) => void;
  caption: string;
}

/** The drawing box, which is also the type scale: the SVG is scaled to its container, so
 * a 900-unit box inside a 288px phone renders `fontSize="10"` axis labels at ~3px. The
 * narrow box is roughly 1:1 with CSS pixels, so the same labels come out legible and the
 * chart stops being a 120px sliver. */
/* H is what sets the rendered height: the SVG scales to its container's width, so at the
 * ~1030px the lens column has beside the rail on a 1440 screen, 900×330 draws ~378px tall
 * — headline, chart and rail then share one 900px fold. Shrinking W instead would have
 * bought the same height by scaling the axis labels down with it. */
const WIDE = { W: 900, H: 330, PAD: { top: 20, right: 16, bottom: 46, left: 68 } };
const NARROW = { W: 330, H: 300, PAD: { top: 14, right: 10, bottom: 44, left: 56 } };

// The net-worth curve, coloured by component. Amber is the beam's alone; the
// components are sea-green / blue tints that hold AA on paper and stay
// separable under deuteranopia (also clipped under the curve and labelled in the
// legend, never colour-only).

// NOTE: this file had its own `fmtAxis` producing `€1.3M` / `€120k` — the fifth money
// format in the app, on the chart most likely to be read beside the others. `money.ts`'s
// `formatEuroTick` is the one compact euro format; the left gutter widened to fit it.

export function TimelineChart({
  months,
  netWorth,
  components,
  band,
  median,
  markers,
  ticks,
  selectedId,
  onSelect,
  caption,
}: Props) {
  const t = useT();
  const uid = useId();
  const narrow = useMediaQuery(BELOW_SM);
  // The month under the pointer, read out below the chart rather than in a floating box:
  // no positioning maths, and it survives the chart being any width.
  const [hovered, setHovered] = useState<number | null>(null);
  const { W, H, PAD } = narrow ? NARROW : WIDE;
  // Year + age under every tick needs ~70 units of width; at 330 that is four labels
  // before they collide, so thin the set rather than let them overlap.
  const shownTicks = narrow ? ticks.filter((_, i) => i % 2 === 0) : ticks;
  const n = months.length;
  const zeros = () => new Array(n).fill(0) as number[];

  const scaleX = linearScale(0, n - 1, PAD.left, W - PAD.right);
  const x = (i: number) => scaleX(i);

  const stackDefs = [
    {
      key: "liquid_investments",
      color: SERIES.investments,
      vals: components.liquid_investments ?? zeros(),
    },
    { key: "cash", color: SERIES.cash, vals: components.cash ?? zeros() },
    { key: "home_equity", color: SERIES.homeEquity, vals: components.home_equity ?? zeros() },
    { key: "pension", color: SERIES.pension, vals: components.pension ?? zeros() },
  ];

  // The scale follows the net-worth line and, when it is drawn, the whole beam — NOT
  // the gross composition, whose home value or a cash shortfall would otherwise dwarf
  // both. The composition is drawn behind and clipped to the area under the net-worth
  // line, so it reads as that line partitioned by component rather than a stack with
  // its own runaway height. Without a beam the domain collapses onto the net-worth
  // line, which is the whole point of dropping the cone from the Composition lens.
  const yMax = Math.max(...(band?.p90 ?? []), ...(median ?? []), ...netWorth, 0);
  const yMin = Math.min(0, ...(band?.p10 ?? []), ...(median ?? []), ...netWorth);
  const scaleY = linearScale(yMin, yMax, H - PAD.bottom, PAD.top);
  const pts = (vals: number[]): XY[] => vals.map((v, i) => ({ x: x(i), y: scaleY(v) }));

  // Stacked component areas (positive contributions), clipped to under the curve.
  let cum = zeros();
  const areas = stackDefs.map((c) => {
    const bottom = pts(cum);
    const next = cum.map((v, i) => v + Math.max(0, c.vals[i]));
    const area = { key: c.key, color: c.color, path: buildBandPath(pts(next), bottom) };
    cum = next;
    return area;
  });
  // Clip = the band between the net-worth line and the plot floor.
  const floorY = H - PAD.bottom;
  const underCurve = `${buildLinePath(pts(netWorth))} L${(W - PAD.right).toFixed(2)},${floorY} L${PAD.left.toFixed(2)},${floorY} Z`;

  const beam = band && {
    path: buildBandPath(pts(band.p90), pts(band.p10)),
    median: buildLinePath(pts(band.p50)),
    beacon: { x: x(0), y: scaleY(band.p50[0]) },
  };
  const nwPath = buildLinePath(pts(netWorth));
  const baseY = scaleY(Math.max(yMin, Math.min(yMax, 0)));

  // y gridlines on a round step — even splits of the raw domain read as €1.3M / €2.5M.
  const gridVals = niceTicks(yMin, yMax, 5);

  const gradId = `beam-grad-${uid}`;
  const glowId = `beam-glow-${uid}`;
  const clipId = `beam-clip-${uid}`;
  const underId = `under-curve-${uid}`;

  const activate = (id: number) => (e: KeyboardEvent) => {
    if (e.key === "Enter" || e.key === " ") {
      e.preventDefault();
      onSelect(id);
    }
  };

  // Pointer x -> month index, through the viewBox rather than CSS pixels: the SVG is
  // scaled to its container, so the two are only equal by accident.
  const scrub = (e: PointerEvent<SVGSVGElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    if (rect.width === 0 || n < 2) return;
    const vx = ((e.clientX - rect.left) / rect.width) * W;
    const i = Math.round(((vx - PAD.left) / (W - PAD.right - PAD.left)) * (n - 1));
    setHovered(i >= 0 && i < n ? i : null);
  };

  return (
    <div>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        className="mt-2 w-full touch-none"
        role="img"
        aria-label={caption}
        preserveAspectRatio="xMidYMid meet"
        onPointerMove={scrub}
        onPointerLeave={() => setHovered(null)}
      >
        <style>{`
        .vt-beam-reveal { transform-box: fill-box; transform-origin: left center; animation: vt-beam-grow 1.1s ease-out both; }
        @keyframes vt-beam-grow { from { transform: scaleX(0); } to { transform: scaleX(1); } }
        @media (prefers-reduced-motion: reduce) { .vt-beam-reveal { animation: none; transform: none; } }
      `}</style>
        <defs>
          <linearGradient
            id={gradId}
            gradientUnits="userSpaceOnUse"
            x1={x(0)}
            y1="0"
            x2={x(n - 1)}
            y2="0"
          >
            <stop offset="0" stopColor={BEAM.fill} stopOpacity="0.75" />
            <stop offset="1" stopColor={BEAM.fill} stopOpacity="0.14" />
          </linearGradient>
          <filter id={glowId} x="-20%" y="-20%" width="140%" height="140%">
            <feGaussianBlur stdDeviation="3" />
          </filter>
          <clipPath id={clipId}>
            <rect className="vt-beam-reveal" x={PAD.left} y={0} width={W - PAD.left} height={H} />
          </clipPath>
          <clipPath id={underId}>
            <path d={underCurve} />
          </clipPath>
        </defs>

        {/* y gridlines + labels */}
        {gridVals.map((v) => (
          <g key={v}>
            <line
              x1={PAD.left}
              x2={W - PAD.right}
              y1={scaleY(v)}
              y2={scaleY(v)}
              className="stroke-ink-navy/10 dark:stroke-paper/10"
              strokeWidth="1"
            />
            <text
              x={PAD.left - 6}
              y={scaleY(v) + 3}
              textAnchor="end"
              className="fill-ink-navy/60 dark:fill-paper/60"
              fontSize="10"
            >
              {formatEuroTick(v)}
            </text>
          </g>
        ))}

        {/* The net-worth curve coloured by component, clipped to the area under the
            curve so it never outgrows it. With no beam over it this is the subject, not
            quiet context: the y domain is scaled to it, and the fill goes opaque. At
            0.35 all four colours washed toward the same pale tint against paper, so
            home equity and pension stayed invisible even once the scale was fixed. */}
        <g clipPath={`url(#${underId})`}>
          {areas.map((a) => (
            <path key={a.key} d={a.path} fill={a.color} fillOpacity={band ? 0.35 : 0.9} />
          ))}
        </g>
        <line
          x1={PAD.left}
          x2={W - PAD.right}
          y1={baseY}
          y2={baseY}
          className="stroke-ink-navy/25 dark:stroke-paper/25"
          strokeWidth="1"
        />

        {/* THE BEAM — the one bold element, in front of the composition but behind
          the net-worth curve, revealed once on load */}
        {beam && (
          <g clipPath={`url(#${clipId})`}>
            <path d={beam.path} fill={`url(#${gradId})`} filter={`url(#${glowId})`} />
            <path
              d={beam.median}
              fill="none"
              stroke={BEAM.line}
              strokeWidth="1.5"
              strokeOpacity="0.85"
            />
            <circle
              cx={beam.beacon.x}
              cy={beam.beacon.y}
              r="7"
              fill={BEAM.line}
              filter={`url(#${glowId})`}
            />
            <circle cx={beam.beacon.x} cy={beam.beacon.y} r="3" fill={BEAM.core} />
          </g>
        )}

        <path
          d={nwPath}
          fill="none"
          className="stroke-ink-navy dark:stroke-paper"
          strokeWidth="2.5"
          strokeLinejoin="round"
        />
        {median && (
          <path
            d={buildLinePath(pts(median))}
            fill="none"
            stroke={BEAM.line}
            strokeWidth="2"
            strokeDasharray="6 4"
            strokeLinejoin="round"
          />
        )}

        {/* x-axis ticks: calendar year + primary person's age */}
        {shownTicks.map((tick) => (
          <g key={tick.monthIndex}>
            <line
              x1={x(tick.monthIndex)}
              x2={x(tick.monthIndex)}
              y1={H - PAD.bottom}
              y2={H - PAD.bottom + 4}
              className="stroke-ink-navy/40 dark:stroke-paper/40"
            />
            <text
              x={x(tick.monthIndex)}
              y={H - PAD.bottom + 17}
              textAnchor="middle"
              className="fill-ink-navy/70 dark:fill-paper/70"
              fontSize="11"
            >
              {tick.year}
            </text>
            {tick.age != null && (
              <text
                x={x(tick.monthIndex)}
                y={H - PAD.bottom + 30}
                textAnchor="middle"
                className="fill-ink-navy/70 dark:fill-paper/70"
                fontSize="10"
              >
                {t("chart.age")} {tick.age}
              </text>
            )}
          </g>
        ))}

        {/* the scrub rule, under the pointer */}
        {hovered != null && (
          <line
            x1={x(hovered)}
            x2={x(hovered)}
            y1={PAD.top}
            y2={H - PAD.bottom}
            className="stroke-ink-navy/50 dark:stroke-paper/50"
            strokeWidth="1"
          />
        )}

        {/* milestone markers — keyboard focusable, click/Enter to open details */}
        {markers.map((m) => {
          const mx = x(m.monthIndex);
          const active = m.id === selectedId;
          return (
            <g
              key={m.id}
              role="button"
              tabIndex={0}
              aria-pressed={active}
              aria-label={`Milestone: ${m.label}`}
              onClick={() => onSelect(m.id)}
              onKeyDown={activate(m.id)}
              style={{ cursor: "pointer" }}
            >
              <line
                x1={mx}
                x2={mx}
                y1={PAD.top + 14}
                y2={H - PAD.bottom}
                className="stroke-ink-navy/35 dark:stroke-paper/35"
                strokeWidth={active ? 2 : 1}
                strokeDasharray="3 3"
              />
              <circle
                cx={mx}
                cy={PAD.top + 14}
                r={active ? 6 : 4}
                className="fill-ink-navy dark:fill-paper"
              />
              <text
                x={mx}
                y={PAD.top + 4}
                textAnchor="middle"
                className="fill-ink-navy dark:fill-paper"
                fontSize="10"
                fontWeight={active ? 700 : 400}
              >
                {m.label}
              </text>
            </g>
          );
        })}
      </svg>
      {/* Reserved height, so hovering the chart never reflows the page under it. The
          `role="img"` caption above stays the non-visual reading of the same data —
          this readout is the pointer's equivalent, which Recharts' tooltip was. */}
      <p className="h-5 text-xs tabular-nums text-ink-navy/70 dark:text-paper/70">
        {hovered != null &&
          [
            months[hovered],
            `${t("plan.chart.netWorth")} ${formatEuroTick(netWorth[hovered])}`,
            ...(median ? [`${t("plan.chart.median")} ${formatEuroTick(median[hovered])}`] : []),
            ...(band
              ? [
                  `p10 ${formatEuroTick(band.p10[hovered])}`,
                  `p50 ${formatEuroTick(band.p50[hovered])}`,
                  `p90 ${formatEuroTick(band.p90[hovered])}`,
                ]
              : []),
          ].join(" · ")}
      </p>
    </div>
  );
}
