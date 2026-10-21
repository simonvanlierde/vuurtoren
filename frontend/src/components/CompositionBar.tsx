/** The Today composition bar: a horizontal diverging stacked SVG bar.
 * The adjacent "By kind" dl is the labeled legend and text equivalent — this
 * element is decorative reinforcement, so colour is never the only encoding. */
import { SERIES } from "../lib/chartColors";
import { buildComposition, KIND_COLORS } from "../lib/composition";

const BAR_H = 28;

export function CompositionBar({ kindTotals }: { kindTotals: Record<string, number> }) {
  const c = buildComposition(kindTotals);
  if (!c) return null;
  const segments = [...c.negatives, ...c.positives];
  return (
    <svg
      viewBox={`0 0 100 ${BAR_H}`}
      preserveAspectRatio="none"
      className="h-7 w-full"
      aria-hidden="true"
    >
      {segments.map((s) => (
        <rect
          key={s.kind}
          x={s.startPct}
          y={4}
          width={Math.max(s.widthPct - 0.4, 0.2)}
          height={BAR_H - 8}
          rx={0.6}
          fill={KIND_COLORS[s.kind] ?? SERIES.neutral}
        />
      ))}
      <line
        x1={c.zeroPct}
        x2={c.zeroPct}
        y1={0}
        y2={BAR_H}
        className="stroke-ink-navy/50 dark:stroke-paper/50"
        strokeWidth={0.4}
      />
      <line
        x1={c.netPct}
        x2={c.netPct}
        y1={0}
        y2={BAR_H}
        className="stroke-ink-navy dark:stroke-paper"
        strokeWidth={0.7}
      />
    </svg>
  );
}
