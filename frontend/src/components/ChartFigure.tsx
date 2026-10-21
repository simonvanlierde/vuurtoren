/** The wrapper every Recharts plot sits in, so a chart is one named thing to a screen
 * reader instead of a pile of unlabelled SVG.
 *
 * `role="img"` takes the SVG's contents out of the accessibility tree, which is the point
 * — but it takes anything else inside the element with it, so the spoken summary is a
 * SIBLING, never a child. Charts that already render their figures as visible prose
 * (a caption, a metrics table) pass no `summary`: repeating it would read twice.
 */
import type { ReactNode } from "react";

export function ChartFigure({
  label,
  summary,
  className,
  children,
}: {
  label: string;
  /** The chart's key numbers as one line, e.g. "start € 250.000 · end € 1,2 mln". */
  summary?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <>
      <div className={className} role="img" aria-label={label}>
        {children}
      </div>
      {summary && <p className="sr-only">{summary}</p>}
    </>
  );
}
