/**
 * Thin fetch wrappers + TanStack Query hooks over the FastAPI app in `vuurtoren.api`.
 * Money fields stay strings end to end — components parse them with `money.ts`
 * only at the point they need to add or format, never eagerly.
 */
import {
  keepPreviousData,
  useMutation,
  useQueries,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";
import type { components } from "./api.gen";
import type { TaxField } from "./taxFields";

type Schemas = components["schemas"];

export type Household = Schemas["Household-Output"];

/** `domain.FilingStatus`. Spelled out because that is what the database stores; the
 * US figures are keyed by short suffixes on the Python side only. */
export const FILING_STATUSES = [
  "single",
  "married_filing_separately",
  "married_filing_jointly",
] as const;
export type FilingStatus = (typeof FILING_STATUSES)[number];

/** `us_person` is citizenship, not residence: a US person is taxed by the United States
 * wherever they live, which is the whole reason `tax/us/` exists. */
export type Person = Schemas["Person-Output"];

/** `Account.overlay_treatment` — the citizenship-scoped classification, kept apart from
 * `tax_treatment` (residence-scoped) on purpose. Empty means unclassified, which is a
 * legitimate answer: a Dutch bank account has no US wrapper, only US-taxable interest. */
export const OVERLAY_TREATMENTS = [
  "us.non_pfic",
  "us.pfic_mtm",
  "us.pfic_unelected",
  "us.retirement",
] as const;

/** The classification an ISIN already implies, for prefilling a new account's drawer.
 *
 * An ISIN's first two characters are its issuing country, so a real one says outright
 * whether a fund is US-domiciled — which is exactly what separates `us.non_pfic` (a US
 * fund or individual stocks) from `us.pfic_mtm` (anything else; a UCITS is the usual
 * case). Empty when the identifier is not ISIN-shaped, because the same column holds the
 * literal Yahoo symbol for fetched-price accounts and "VT" says nothing about domicile.
 *
 * Only ever an initial value, never an override of a stored one, and it lands in a visible
 * editable field — a wrong guess is corrected by looking at it. Which matters, because
 * `us.pfic_unelected` stops the projection and a wrong `us.non_pfic` quietly undertaxes.
 */
export function domicileDefault(isin: string | null | undefined): string {
  if (!isin || !/^[A-Za-z]{2}[A-Za-z0-9]{9}\d$/.test(isin)) return "";
  return isin.slice(0, 2).toUpperCase() === "US" ? "us.non_pfic" : "us.pfic_mtm";
}

export type AccountKind = Schemas["AccountKind"];
export type PriceSource = Schemas["PriceSource"];
/** Quote currencies the price layer can convert (`domain.Currency`). Reporting is
 * always EUR — this is only what a foreign quote is converted *from*. */
export const CURRENCIES = ["EUR", "USD"] as const;
export type Currency = (typeof CURRENCIES)[number];

export type Account = Schemas["Account-Output"];
export type PricePoint = Schemas["PricePointOut-Output"];

export interface RefreshOutcome {
  account_id: number;
  account_name: string;
  ok: boolean;
  value_eur: string | null;
  error: string | null;
}

/** The four monthly flow series `/api/project` always includes. */
export type FlowTotals = Schemas["FlowTotalsOut"];

/** `/api/project` with `n_runs > 1`: percentile bands, a success probability and the
 * mortality overlay's two inputs. Net worth here is plain euro floats, not Money strings.
 * `seed` is null in sequential mode; `start_years` is set only there (run r *is* start
 * year `start_years[r]`). */
export type MonteCarloResult = Schemas["MonteCarloOut"];
export type MonteCarloMode = MonteCarloResult["mode"];

/** The assumptions a request sends; a field left out keeps the server's default. */
export type ProjectAssumptions = Schemas["AssumptionsIn"];

/** Tax-figure overrides: `{country: {year: {field: value}}}`. */
export type TaxOverrides = NonNullable<InlineOverrides["tax"]>;

/** Inline scenario overrides: the drawer preview and the tax panel's live edits. */
export type InlineOverrides = Schemas["ScenarioOverrides-Input"];

/** `PlanRequestBase`: the plan half every analysis request shares. `overrides` is
 * mutually exclusive with `scenario_id` server-side. */
export type PlanRequestBody = Pick<
  Schemas["ProjectRequest"],
  "household_id" | "scenario_id" | "start" | "assumptions" | "overrides"
>;

/** `min_end_net_worth` is the bequest floor: a Monte Carlo run counts as a success only
 * if it ends with at least this much net worth. The deterministic run ignores it. */
export type ProjectRequestBody = Schemas["ProjectRequest"];

/** `/api/project` at `n_runs=1`. `net_worth`/`components`/`investment_income` are
 * (n_runs, n_months) matrices even at n_runs=1: index run 0 for the single path. */
export type ProjectionResponse = Schemas["ProjectionOut"];

export interface TaxConfigResponse {
  country: string;
  year: number;
  source_year: number;
  /** ISO code the country's money figures are denominated in. Only the US set is not EUR. */
  currency: string;
  /** Every `tax_treatment` string the country's regime accepts, sorted. The account
   * editor's picker is this list — the vocabulary is the regime's, not the UI's. */
  valid_treatments: string[];
  fields: Record<string, TaxField>;
}

export type CashFlowKind = Schemas["CashFlowKind"];

export type CashFlow = Schemas["CashFlow-Output"];
export type Milestone = Schemas["Milestone-Output"];

export class ApiError extends Error {
  readonly status: number;
  readonly detail: unknown;

  constructor(status: number, detail: unknown, message: string) {
    super(message);
    this.status = status;
    this.detail = detail;
  }
}

async function raiseApiError(res: Response, method: string, path: string): Promise<never> {
  let detail: unknown = null;
  try {
    detail = ((await res.json()) as { detail?: unknown }).detail ?? null;
  } catch {
    // non-JSON error body (empty 500, proxy page) — the status alone carries it
  }
  throw new ApiError(res.status, detail, `${method} /api/${path} failed: ${res.status}`);
}

/** One request path for both builds: the worker under VITE_PYODIDE, the network otherwise.
 * `path` may carry a query string (e.g. `refresh-prices?household_id=1`) — passed through.
 * The worker module is dynamically imported so the server build (PYODIDE=false, a build-time
 * constant) dead-code-eliminates pyodide entirely. */
async function apiFetch(
  method: string,
  path: string,
  body?: unknown,
  signal?: AbortSignal,
): Promise<Response> {
  // Raw env check (not the re-exported PYODIDE) so Vite replaces it with a literal and
  // Rollup drops the import() — and thus the worker + pyodide — from the server build.
  if (import.meta.env.VITE_PYODIDE === "1") {
    const { pyodideFetch } = await import("../pyodide/client");
    return pyodideFetch(method, path, body, signal);
  }
  return fetch(`/api/${path}`, {
    method,
    signal,
    ...(body !== undefined && {
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    }),
  });
}

/** `signal` is React Query's: passing it lets a superseded query cancel its request. */
async function apiGet<T>(path: string, signal?: AbortSignal): Promise<T> {
  const res = await apiFetch("GET", path, undefined, signal);
  if (!res.ok) await raiseApiError(res, "GET", path);
  return res.json() as Promise<T>;
}

async function apiPost<T>(path: string, body?: unknown, signal?: AbortSignal): Promise<T> {
  const res = await apiFetch("POST", path, body, signal);
  if (!res.ok) await raiseApiError(res, "POST", path);
  return res.json() as Promise<T>;
}

async function apiPut<T>(path: string, body: unknown): Promise<T> {
  const res = await apiFetch("PUT", path, body);
  if (!res.ok) await raiseApiError(res, "PUT", path);
  return res.json() as Promise<T>;
}

async function apiDelete(path: string): Promise<void> {
  const res = await apiFetch("DELETE", path);
  if (!res.ok) await raiseApiError(res, "DELETE", path);
}

/** POST/PUT/DELETE hooks for one `_register_crud` table (`api/crud.py`). Any entity
 * mutation invalidates every query: accounts feed projections feed charts —
 * a scoped invalidation list would silently drift. */
export function makeCrudHooks<TIn, TOut>(path: string) {
  function useCreate() {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: (body: TIn) => apiPost<TOut>(path, body),
      onSuccess: () => queryClient.invalidateQueries(),
    });
  }
  function useUpdate() {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: ({ id, body }: { id: number; body: TIn }) => apiPut<TOut>(`${path}/${id}`, body),
      onSuccess: () => queryClient.invalidateQueries(),
    });
  }
  function useDelete() {
    const queryClient = useQueryClient();
    return useMutation({
      mutationFn: (id: number) => apiDelete(`${path}/${id}`),
      onSuccess: () => queryClient.invalidateQueries(),
    });
  }
  return { useCreate, useUpdate, useDelete };
}

export type AccountIn = Schemas["AccountIn"];
export type CashFlowIn = Schemas["CashFlowIn"];
export type PersonIn = Schemas["PersonIn"];
export type MilestoneIn = Schemas["MilestoneIn"];
export type HouseholdIn = Schemas["HouseholdIn"];

export const accountApi = makeCrudHooks<AccountIn, Account>("accounts");
export const cashFlowApi = makeCrudHooks<CashFlowIn, CashFlow>("cash-flows");
export const personApi = makeCrudHooks<PersonIn, Person>("people");
export const milestoneApi = makeCrudHooks<MilestoneIn, Milestone>("milestones");
export const householdApi = makeCrudHooks<HouseholdIn, Household>("households");

export function useHouseholds() {
  return useQuery({
    queryKey: ["households"],
    queryFn: ({ signal }) => apiGet<Household[]>("households", signal),
  });
}

export function usePeople() {
  return useQuery({
    queryKey: ["people"],
    queryFn: ({ signal }) => apiGet<Person[]>("people", signal),
  });
}

export function useAccounts() {
  return useQuery({
    queryKey: ["accounts"],
    queryFn: ({ signal }) => apiGet<Account[]>("accounts", signal),
  });
}

export function usePricePoints() {
  return useQuery({
    queryKey: ["price-points"],
    queryFn: ({ signal }) => apiGet<PricePoint[]>("price-points", signal),
  });
}

export function useCashFlows() {
  return useQuery({
    queryKey: ["cash-flows"],
    queryFn: ({ signal }) => apiGet<CashFlow[]>("cash-flows", signal),
  });
}

export function useMilestones() {
  return useQuery({
    queryKey: ["milestones"],
    queryFn: ({ signal }) => apiGet<Milestone[]>("milestones", signal),
  });
}

// A fixed seed and run count keep THE BEAM identical across renders;
// 750 runs stays interactive while the cone is smooth.
const BEAM_SEED = 20260724;
const BEAM_RUNS = 750;

export function useProjectionBands(request: ProjectRequestBody) {
  return useQuery({
    queryKey: ["project-bands", request, BEAM_SEED, BEAM_RUNS],
    queryFn: ({ signal }) =>
      apiPost<MonteCarloResult>(
        "project",
        { ...request, n_runs: BEAM_RUNS, seed: BEAM_SEED },
        signal,
      ),
    placeholderData: keepPreviousData,
  });
}

/** GET /api/export as a document — used to build a client-side download in both builds.
 * Goes through apiFetch, so it works in the browser build where there is no server to
 * navigate an `<a href="/api/export">` to. */
export function fetchExportDoc(): Promise<unknown> {
  return apiGet<unknown>("export");
}

export function useRefreshPrices() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (householdId: number) =>
      apiPost<RefreshOutcome[]>(`refresh-prices?household_id=${householdId}`),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["price-points"] });
    },
  });
}

/** POST /api/import — load a whole household from an export document. The server
 * imports only into an empty database (it 409s on any id collision), so the caller
 * surfaces that message rather than merging. Invalidates every query on success. */
export function useImportHousehold() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (doc: unknown) => apiPost<{ household_id: number }>("import", doc),
    onSuccess: () => queryClient.invalidateQueries(),
  });
}

/** DELETE /api/households/{id}/all — the household and everything in it, so the
 * database is empty again: the way out of the example household, and what lets Import
 * restore a saved export. Invalidates every query on success. */
export function useDeleteHouseholdAll() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (householdId: number) => apiDelete(`households/${householdId}/all`),
    onSuccess: () => queryClient.invalidateQueries(),
  });
}

/** POST /api/price-points/manual — the server computes value_eur,
 * converting a foreign per-unit price at the ECB daily rate. */
export function useRecordManualPrice() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: { account_id: number; date: string; price?: string; value?: string }) =>
      apiPost<PricePoint>("price-points/manual", body),
    onSuccess: () => queryClient.invalidateQueries(),
  });
}

/** Behind an explicit Run button only — never on mount or on input
 * change, unlike the live-projection queries above. The body is the plan's own request
 * (the one the preview beam sends) plus the run knobs, so Run simulates the plan on screen. */
export function useMonteCarloProjection() {
  return useMutation({
    mutationFn: (
      body: ProjectRequestBody & {
        /** Omitted in sequential mode: the dataset fixes the run count, not the caller. */
        n_runs?: number;
        seed?: number;
        mode: MonteCarloMode;
      },
    ) => apiPost<MonteCarloResult>("project", body),
  });
}

/** POST /api/solve — bisect the pure projection for the monthly spending/contribution
 * that hits a goal. Behind a Run button. `solved_monthly` is null when the goal has no
 * solution in range — the UI says so rather than lying. */
export type SolveResult = Schemas["SolveOut"];
export type SolveKnob = SolveResult["knob"];

export type SolveGoal = Schemas["SolveGoal"];
export type SolveRequestBody = Schemas["SolveRequest"];

export function useSolve() {
  return useMutation({
    mutationFn: (body: SolveRequestBody) => apiPost<SolveResult>("solve", body),
  });
}

/** POST /api/retirement — when can I stop, and what are the odds if I do.
 * Exactly one of `at_date` / `probability`; sending both is a 400. */
export type RetirementRequestBody = Schemas["RetirementRequest"];

/** `fi_date` is the 4%-rule FI date from the same run — shown *beside* the solved date,
 * never instead of it. They answer different questions and routinely disagree. */
export type RetirementResult = Schemas["RetirementOut"];

/** Behind an explicit Run button only: this bisects over Monte Carlo projections and is
 * the most expensive thing in the app. */
export function useRetirement() {
  return useMutation({
    mutationFn: (body: RetirementRequestBody) => apiPost<RetirementResult>("retirement", body),
  });
}

/** POST /api/sweep — the spending-vs-success curve: solve shows one
 * answer, this shows the whole shape. Behind a Run button; it is many projections. */
export type SweepRequestBody = Schemas["SweepRequest"];

export type SweepResult = Schemas["SweepOut"];

export function useSweep() {
  return useMutation({
    mutationFn: (body: SweepRequestBody) => apiPost<SweepResult>("sweep", body),
  });
}

/** POST /api/sensitivity — the tornado: move one assumption at a time and
 * rank the movers. Deterministic and cheap (~8 projections), so it runs on request change
 * while its tab is open rather than behind a button, unlike solve and sweep. */
export type SensitivityResult = Schemas["SensitivityOut"];
/** `delta` is the absolute move applied, e.g. 0.01 for a percentage point. `low`/`high`
 * are the metric with the knob moved down / up; null means FI was never reached. */
export type SensitivityRow = Schemas["SensitivityRowOut"];
export type SensitivityKnob = SensitivityRow["knob"];

export type SensitivityRequestBody = Schemas["SensitivityRequest"];

export function useSensitivity(request: SensitivityRequestBody) {
  return useQuery({
    queryKey: ["sensitivity", request],
    queryFn: ({ signal }) => apiPost<SensitivityResult>("sensitivity", request, signal),
    placeholderData: keepPreviousData,
  });
}

/** The deterministic projection, re-run on every request change ("live
 * sliders ... re-run on every drag"). `placeholderData` keeps the last chart on
 * screen while a new request is in flight, instead of flashing to a loading state. */
export function useProjection(request: ProjectRequestBody) {
  return useQuery({
    queryKey: ["project", request],
    queryFn: ({ signal }) => apiPost<ProjectionResponse>("project", request, signal),
    placeholderData: keepPreviousData,
  });
}

/** One US person's FBAR/FATCA worksheet. Money arrives as strings, like every other
 * money field here — `peak_usd` is a dollar figure and never a float. */
export interface FbarWorksheet {
  person_id: number;
  person_name: string;
  filing_status: FilingStatus;
  accounts: {
    account_id: number;
    name: string;
    peak_local: string;
    year_end_local: string;
    peak_usd: string;
    year_end_usd: string;
  }[];
  aggregate_peak_usd: string;
  aggregate_year_end_usd: string;
  fbar_triggered: boolean;
  fbar_threshold_usd: string;
  fatca_triggered: boolean;
  /** Which of the two Form 8938 tests crossed — either alone is enough to trigger. */
  fatca_trigger_reason: "both" | "last_day" | "any_time" | null;
  fatca_last_day_threshold_usd: string;
  fatca_any_time_threshold_usd: string;
}

export interface FbarResponse {
  year: number;
  rate: { record_date: string; exchange_rate: string } | null;
  /** Empty for a household with no US person — a real answer, not an error. */
  worksheets: FbarWorksheet[];
}

/** No projected year has a published Treasury rate, so the caller always supplies one.
 * `usd_per_eur_override` is Treasury's own convention: foreign currency per one dollar. */
export function useFbarWorksheet(
  request: ProjectRequestBody,
  year: number,
  usdPerEurOverride: string,
  enabled: boolean,
) {
  const body = { ...request, year, usd_per_eur_override: usdPerEurOverride };
  return useQuery({
    queryKey: ["fbar", body],
    queryFn: ({ signal }) => apiPost<FbarResponse>("reporting/fbar", body, signal),
    enabled,
    placeholderData: keepPreviousData,
  });
}

export function useTaxConfig(country: string | undefined, year: number) {
  return useQuery({
    queryKey: ["tax-config", country, year],
    queryFn: ({ signal }) =>
      apiGet<TaxConfigResponse>(`tax-config?year=${year}&country=${country}`, signal),
    enabled: country !== undefined,
    placeholderData: keepPreviousData,
    // The shipped figures for (country, year) only change with a new build. With the
    // default staleTime of 0, every panel that mounts (each lens's tax tab, the account
    // drawer) fetched them again.
    staleTime: Number.POSITIVE_INFINITY,
  });
}

/** What a first-time reader needs in order to judge the numbers in front of them:
 * whose they are, and what the model does not cover. */
export interface Meta {
  /** The stored household is still the committed fictional one. Matched on names by the
   * server, so it stops being true the moment a visitor puts their own in. */
  example_data: boolean;
  tax_country: string | null;
  limitations: { direction: "understates" | "overstates" | "either"; nl: string; en: string }[];
}

export function useMeta() {
  return useQuery({
    queryKey: ["meta"],
    queryFn: ({ signal }) => apiGet<Meta>("meta", signal),
  });
}

/** The country codes with a registered tax regime — the household editor's options.
 * Static for a build, so it never goes stale within a session. */
export function useTaxCountries() {
  return useQuery({
    queryKey: ["tax-countries"],
    queryFn: ({ signal }) => apiGet<string[]>("tax-countries", signal),
    staleTime: Number.POSITIVE_INFINITY,
  });
}

// --- Scenario comparison ---

/** A saved scenario (GET/POST /api/scenarios). A non-empty `overrides.tax` group is
 * the user-edited-rate marker: at least one rate was hand-set, so the
 * scenario must never render as if it came from the Belastingdienst. */
export type Scenario = Schemas["Scenario-Output"];
/** What the scenario templates build: `ScenarioIn` with its name and overrides set. */
export type ScenarioCreate = Required<
  Pick<Schemas["ScenarioIn"], "household_id" | "name" | "overrides">
>;

export function useScenarios() {
  return useQuery({
    queryKey: ["scenarios"],
    queryFn: ({ signal }) => apiGet<Scenario[]>("scenarios", signal),
  });
}

export function useCreateScenario() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (body: ScenarioCreate) => apiPost<Scenario>("scenarios", body),
    onSuccess: () => queryClient.invalidateQueries({ queryKey: ["scenarios"] }),
  });
}

/** Deterministic net-worth line per selected scenario. `useProjection`
 * fetches the single baseline line; this batches the variable-length list of selected
 * scenarios into one `useQueries`, keyed identically so a scenario shown elsewhere is
 * served from cache. Response shape is `ProjectionResponse` (net_worth is a matrix —
 * slice run 0). `request` must share the baseline's assumptions so columns are
 * comparable; the API rejects `scenario_id` together with `overrides`, so callers
 * must strip that field before passing `request` in. */
export function useScenarioProjections(request: ProjectRequestBody, scenarioIds: number[]) {
  return useQueries({
    queries: scenarioIds.map((scenario_id) => ({
      queryKey: ["project", { ...request, scenario_id }],
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        apiPost<ProjectionResponse>("project", { ...request, scenario_id }, signal),
    })),
  });
}

/** Success probability per column, behind the Run button (Monte Carlo runs
 * only on demand). One shared fixed seed and run count across every column keeps the
 * probabilities comparable. `scenarioId === null` is the baseline (no override).
 * `request` must be `overrides`-free for the same reason as `useScenarioProjections`. */
export function useScenarioSuccess(
  request: ProjectRequestBody,
  targets: (number | null)[],
  seed: number,
  enabled: boolean,
) {
  return useQueries({
    queries: targets.map((scenarioId) => ({
      queryKey: ["project-success", { ...request, scenario_id: scenarioId }, seed],
      queryFn: ({ signal }: { signal: AbortSignal }) =>
        apiPost<MonteCarloResult>(
          "project",
          {
            ...request,
            n_runs: 1000,
            seed,
            ...(scenarioId !== null && { scenario_id: scenarioId }),
          },
          signal,
        ),
      enabled,
      staleTime: Infinity,
    })),
  });
}
