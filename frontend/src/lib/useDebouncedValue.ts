import { useEffect, useState } from "react";

/** The latest `value` after `delayMs` of no further changes — commit-on-release for the
 * projection sliders: rapid drags coalesce, and only the settled value drives a re-run.
 * Replaces `useDeferredValue`, which still fired intermediate runs during a drag — costly
 * once each run is a ~180ms Pyodide call. Returns the exact `value` reference once settled,
 * so a reference compare (`value === settled`) is a "calculating" signal. */
export function useDebouncedValue<T>(value: T, delayMs: number): T {
  const [settled, setSettled] = useState(value);
  useEffect(() => {
    const id = setTimeout(() => setSettled(value), delayMs);
    return () => clearTimeout(id);
  }, [value, delayMs]);
  return settled;
}
