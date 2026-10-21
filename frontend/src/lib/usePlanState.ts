/** The Plan canvas's shared state: assumptions sliders, tax-year overrides and the
 * request bodies they build, so every lens and the deck read and drive the same plan. */
import { useMemo, useState } from "react";
import {
  type Household,
  type InlineOverrides,
  type PlanRequestBody,
  type ProjectRequestBody,
  useHouseholds,
} from "./api";
import { decodeShareState, encodeShareState } from "./urlHash";
import { useDebouncedValue } from "./useDebouncedValue";

// Server defaults (`AssumptionsIn` in `api/schemas.py`) — mirrored here only for the sliders'
// starting position; omitted fields in the request keep the server's own defaults.
const DEFAULT_INFLATION = 0.02;
const DEFAULT_SWR = 0.04;
const DEFAULT_HOUSE_APPRECIATION = 0.02;

function firstOfThisMonth(): string {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth() + 1).padStart(2, "0")}-01`;
}

export function usePlanState() {
  const households = useHouseholds();
  const household: Household | undefined = households.data?.[0];

  const start = useMemo(firstOfThisMonth, []);
  // A shared link seeds the assumption knobs
  // once on mount; from there the sliders own them. Read lazily so it happens exactly once.
  const [shared] = useState(() =>
    decodeShareState(typeof window === "undefined" ? "" : window.location.hash),
  );
  const [inflation, setInflation] = useState(shared.inflation ?? DEFAULT_INFLATION);
  const [swr, setSwr] = useState(shared.swr ?? DEFAULT_SWR);
  const [houseAppreciation, setHouseAppreciation] = useState(
    shared.houseAppreciation ?? DEFAULT_HOUSE_APPRECIATION,
  );
  // NOTE: no "return" slider here — per-account `return_assumption` overrides are a
  // deferred group; only the assumptions that are global to the plan
  // (inflation, SWR, house appreciation) get a live slider in this view.
  // Display-only: deflate the charts to start-date euros. Never part of the request —
  // the engine always projects in nominal euros; this only transforms what's drawn.
  const [realTerms, setRealTerms] = useState(shared.realTerms ?? false);
  // Bequest floor: folded into the request, where it shapes the Monte Carlo
  // success probability only. Empty string = no floor (plain solvency).
  const [minEndNetWorth, setMinEndNetWorth] = useState(shared.minEndNetWorth ?? "");
  const [taxYear, setTaxYear] = useState(() => new Date().getFullYear());
  const [overrides, setOverrides] = useState<Record<number, Record<string, string>>>({});
  const [previewOverrides, setPreviewOverrides] = useState<InlineOverrides | null>(null);
  const [milestoneEditor, setMilestoneEditor] = useState<number | "new" | null>(null);

  const hasEdits = Object.values(overrides).some((fields) => Object.keys(fields).length > 0);

  // The rail marks a moved slider; it now also offers the way back, which it never did.
  const assumptionsAreDefault =
    inflation === DEFAULT_INFLATION &&
    swr === DEFAULT_SWR &&
    houseAppreciation === DEFAULT_HOUSE_APPRECIATION;

  function resetAssumptions() {
    setInflation(DEFAULT_INFLATION);
    setSwr(DEFAULT_SWR);
    setHouseAppreciation(DEFAULT_HOUSE_APPRECIATION);
  }

  // The plan every analysis runs on: Solve, Sweep and Early retirement send it with their
  // own knobs. The Monte Carlo floor is not part of it; `requestBody` adds that.
  const analysisBase: PlanRequestBody = useMemo(() => {
    const body: PlanRequestBody = {
      start,
      assumptions: { inflation, swr, house_appreciation: houseAppreciation },
    };
    // A drawer preview and live tax edits travel together as one unsaved scenario.
    if (previewOverrides) body.overrides = previewOverrides;
    if (hasEdits && household) {
      const byYear = Object.fromEntries(
        Object.entries(overrides).filter(([, fields]) => Object.keys(fields).length > 0),
      );
      body.overrides = { ...body.overrides, tax: { [household.tax_country]: byYear } };
    }
    return body;
  }, [start, inflation, swr, houseAppreciation, overrides, hasEdits, household, previewOverrides]);

  // The bequest floor as a number, or undefined for none (plain solvency).
  const parsedFloor = Number(minEndNetWorth);
  const floor =
    minEndNetWorth.trim() !== "" && Number.isFinite(parsedFloor) ? parsedFloor : undefined;
  const requestBody: ProjectRequestBody = useMemo(
    () => (floor === undefined ? analysisBase : { ...analysisBase, min_end_net_worth: floor }),
    [analysisBase, floor],
  );

  // Re-run on slider *commit*, not every drag frame (see `useDebouncedValue`).
  // `isCalculating` is true while a change is settling: it drives the "calculating…" cue.
  const deferredRequest = useDebouncedValue(requestBody, 250);
  const isCalculating = requestBody !== deferredRequest;
  // The live analysis half for the Sensitivity tab: it takes no floor.
  const deferredAnalysisBase = useDebouncedValue(analysisBase, 250);
  // Saved-scenario columns: the API rejects `scenario_id` together with `overrides`, and
  // live edits must not leak into a saved scenario's column anyway.
  const scenarioBase: ProjectRequestBody = useMemo(() => {
    const { overrides: _overrides, ...rest } = deferredRequest;
    return rest;
  }, [deferredRequest]);

  function shareUrl(): string {
    const hash = encodeShareState({
      inflation,
      swr,
      houseAppreciation,
      realTerms,
      minEndNetWorth,
    });
    const { origin, pathname } = window.location;
    return hash ? `${origin}${pathname}#${hash}` : `${origin}${pathname}`;
  }

  function editField(name: string, value: string) {
    setOverrides((prev) => ({ ...prev, [taxYear]: { ...prev[taxYear], [name]: value } }));
  }

  function resetField(name: string) {
    setOverrides((prev) => {
      if (!prev[taxYear] || !(name in prev[taxYear])) return prev;
      const { [name]: _dropped, ...rest } = prev[taxYear];
      return { ...prev, [taxYear]: rest };
    });
  }

  return {
    inflation,
    swr,
    houseAppreciation,
    setInflation,
    setSwr,
    setHouseAppreciation,
    assumptionsAreDefault,
    resetAssumptions,
    realTerms,
    setRealTerms,
    minEndNetWorth,
    setMinEndNetWorth,
    taxYear,
    setTaxYear,
    overrides,
    editField,
    resetField,
    hasEdits,
    household,
    shareUrl,
    analysisBase,
    deferredAnalysisBase,
    floor,
    deferredRequest,
    scenarioBase,
    isCalculating,
    setPreviewOverrides,
    milestoneEditor,
    setMilestoneEditor,
  };
}
