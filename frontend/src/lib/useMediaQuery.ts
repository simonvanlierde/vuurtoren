import { useEffect, useState } from "react";

/** Subscribe to a CSS media query from JS.
 *
 * Tailwind handles anything that is purely presentational; this is for the cases where a
 * *value* has to change, not a class — Recharts takes its axis width and category count as
 * props, and no stylesheet can thin a 60-bar series down to something a 320px plot can
 * actually draw. */
export function useMediaQuery(query: string): boolean {
  const [matches, setMatches] = useState(() => window.matchMedia(query).matches);

  useEffect(() => {
    const list = window.matchMedia(query);
    const onChange = () => setMatches(list.matches);
    onChange();
    list.addEventListener("change", onChange);
    return () => list.removeEventListener("change", onChange);
  }, [query]);

  return matches;
}

/** The `sm` breakpoint, phrased as "narrower than", so it reads the same way the
 * `sm:` class prefix does in the markup it sits beside. */
export const BELOW_SM = "(width < 40rem)";

/** The `lg` breakpoint, where the assumption rail stops being a collapsible strip and
 * becomes a permanent column beside the chart. A `<details>` cannot be forced open by
 * CSS, so that one needs the query as a value. */
export const FROM_LG = "(width >= 64rem)";
