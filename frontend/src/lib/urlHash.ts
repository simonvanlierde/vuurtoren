/** Encode the shareable view-state — the assumption knobs — into the URL hash.
 * A shared link carries the numbers in it,
 * so the UI shows a visible privacy warning rather than a quiet copy button.
 *
 * Assumption knobs only, not tax overrides or scenario selection: that is the honest
 * "weergave" today. The full-scenario-in-hash version belongs with the browser build. */

export interface ShareState {
  inflation?: number;
  swr?: number;
  houseAppreciation?: number;
  realTerms?: boolean;
  minEndNetWorth?: string;
}

export function encodeShareState(s: ShareState): string {
  const p = new URLSearchParams();
  if (s.inflation != null) p.set("inflation", String(s.inflation));
  if (s.swr != null) p.set("swr", String(s.swr));
  if (s.houseAppreciation != null) p.set("house", String(s.houseAppreciation));
  if (s.realTerms) p.set("real", "1");
  if (s.minEndNetWorth) p.set("floor", s.minEndNetWorth);
  return p.toString();
}

export function decodeShareState(hash: string): ShareState {
  const p = new URLSearchParams(hash.replace(/^#/, ""));
  const out: ShareState = {};
  // A malformed number in a hand-edited link is dropped, not applied as NaN.
  const num = (key: string): number | undefined => {
    if (!p.has(key)) return undefined;
    const n = Number(p.get(key));
    return Number.isFinite(n) ? n : undefined;
  };
  const inflation = num("inflation");
  if (inflation != null) out.inflation = inflation;
  const swr = num("swr");
  if (swr != null) out.swr = swr;
  const house = num("house");
  if (house != null) out.houseAppreciation = house;
  if (p.get("real") === "1") out.realTerms = true;
  const floor = p.get("floor");
  if (floor && Number.isFinite(Number(floor))) out.minEndNetWorth = floor;
  return out;
}
