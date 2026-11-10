/** The one legend every multi-series chart uses. It sits outside `ChartFigure`, whose
 * `role="img"` would hide it from a screen reader, so the series names are read as text.
 * The mark carries the colour and, for lines, the dash, so series also separate without
 * hue; the label stays ink or paper because it is not carrying the encoding. */
import type { ReactNode } from "react";
import { cn } from "@/lib/utils";

export interface LegendItem {
  key: string;
  label: ReactNode;
  color: string;
  /** "swatch" for areas and bars, "line" for lines. */
  mark: "swatch" | "line";
  /** SVG stroke-dasharray, for a dashed or dotted line. */
  dash?: string;
}

export function ChartLegend({
  items,
  className,
}: {
  items: readonly LegendItem[];
  className?: string;
}) {
  return (
    <ul
      className={cn(
        "flex flex-wrap gap-x-5 gap-y-1 text-xs text-ink-navy/70 dark:text-paper/70",
        className,
      )}
    >
      {items.map((item) => (
        <li key={item.key} className="flex items-center gap-1.5">
          {item.mark === "swatch" ? (
            <span
              aria-hidden="true"
              className="inline-block size-2.5 rounded-sm"
              style={{ backgroundColor: item.color }}
            />
          ) : (
            <svg aria-hidden="true" width="18" height="4" className="overflow-visible">
              <line
                x1="0"
                x2="18"
                y1="2"
                y2="2"
                stroke={item.color}
                strokeWidth="2"
                strokeDasharray={item.dash}
              />
            </svg>
          )}
          {item.label}
        </li>
      ))}
    </ul>
  );
}
