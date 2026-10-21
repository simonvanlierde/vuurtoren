import { useCallback, useEffect, useState } from "react";

export const DEFAULT_VIEW = "today";

export type PlanLens = "opbouw" | "onzekerheid" | "scenarios";

/** Old six-view hashes keep working after the four-surface restructure;
 * the deep ones land on the lens that replaced them. */
const LEGACY: Record<string, string> = {
  accounts: "today",
  timeline: "plan",
  projection: "plan",
  "monte-carlo": "plan/onzekerheid",
  scenarios: "plan/scenarios",
  "cash-flow": "flows",
};

function resolve(hash: string): string {
  const raw = hash.replace(/^#/, "") || DEFAULT_VIEW;
  return LEGACY[raw] ?? raw;
}

/** Pure: extracted so it's testable without touching `window`. */
export function viewFromHash(hash: string): string {
  return resolve(hash).split("/")[0];
}

export function lensFromHash(hash: string): PlanLens {
  const segment = resolve(hash).split("/")[1];
  return segment === "onzekerheid" || segment === "scenarios" ? segment : "opbouw";
}

export function hashForLens(lens: PlanLens): string {
  return lens === "opbouw" ? "plan" : `plan/${lens}`;
}

/** Tabs-over-`location.hash`, no router. */
export function useHash(): [string, (view: string) => void] {
  const [view, setView] = useState(() => viewFromHash(window.location.hash));

  useEffect(() => {
    const onHashChange = () => setView(viewFromHash(window.location.hash));
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  const navigate = useCallback((next: string) => {
    window.location.hash = next;
  }, []);

  return [view, navigate];
}

/** Like `useHash`, but returns the raw hash rather than the resolved view — the
 * lens switch needs the `plan/<lens>` segment `useHash` throws away. */
export function useRawHash(): string {
  const [hash, setHash] = useState(() => window.location.hash);

  useEffect(() => {
    const onHashChange = () => setHash(window.location.hash);
    window.addEventListener("hashchange", onHashChange);
    return () => window.removeEventListener("hashchange", onHashChange);
  }, []);

  return hash;
}
