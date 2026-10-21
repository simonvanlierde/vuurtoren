/** The Onzekerheid (uncertainty) lens: THE BEAM — the p10–p90 Monte-Carlo cone —
 * minus its own headline block, which the strip owns via the success-probability
 * slot. Run controls live in the shared deck's "Settings" tab. The cone is drawn only
 * here, on the lens whose subject it is. */
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { TimelineChart } from "../../components/TimelineChart";
import {
  type MonteCarloMode,
  useMonteCarloProjection,
  usePeople,
  useProjectionBands,
} from "../../lib/api";
import { useLocale, useT } from "../../lib/i18n";
import { formatEuros, formatPercent } from "../../lib/money";
import { toReal } from "../../lib/realTerms";
import { failedStartYears } from "../../lib/sequential";
import { yearTicks } from "../../lib/timeline";
import type { usePlanState } from "../../lib/usePlanState";
import { CsvButton } from "./CsvButton";
import { Deck } from "./Deck";
import { FireDateHistogram } from "./FireDateHistogram";
import type { HeadlineSlot } from "./HeadlineStrip";
import { OutcomesPanel } from "./OutcomesPanel";

const RUN_OPTIONS = [1_000, 5_000, 10_000] as const;

/** THE BEAM + success probability. Monte Carlo only ever
 * runs behind the explicit Run button in the deck's Settings tab — never on
 * mount, never on a control change, unlike the live sliders in the canvas's
 * assumption rail. */
export function OnzekerheidLens({
  plan,
  setSlot,
}: {
  plan: ReturnType<typeof usePlanState>;
  setSlot: (s: HeadlineSlot) => void;
}) {
  const t = useT();
  const [locale] = useLocale();
  const people = usePeople();
  const [nRuns, setNRuns] = useState<number>(1_000);
  const [seedText, setSeedText] = useState("");
  const [mode, setMode] = useState<MonteCarloMode>("gaussian");
  // Sequential runs the dataset's start years, so neither the run count nor the seed
  // does anything: grey them out rather than accept input the server will ignore.
  const sequential = mode === "sequential";
  const mutation = useMonteCarloProjection();
  // The 750-run beam the Opbouw lens already computed, off the same cache key — so this
  // lens opens on the answer instead of a dash and 500px of blank canvas. Run still owns
  // every *expensive* simulation; it now refines a shown result rather than being the
  // price of admission.
  const preview = useProjectionBands(plan.deferredRequest);
  const result = mutation.data ?? preview.data;
  const isPreview = mutation.data === undefined && preview.data !== undefined;

  // Real-terms toggle: deflate the whole cone by the run's inflation factor
  // before it becomes chart rows, so every band on the fan reads in start-date euros.
  const bands = useMemo(() => {
    if (!result) return null;
    if (!plan.realTerms) return result.bands;
    const f = result.inflation_factor;
    return {
      p10: toReal(result.bands.p10, f),
      p50: toReal(result.bands.p50, f),
      p90: toReal(result.bands.p90, f),
    };
  }, [result, plan.realTerms]);

  // The same year+age axis the Composition lens draws, off the shared builder — two
  // views of one plan must not disagree about where 2040 is.
  const ticks = useMemo(
    () => yearTicks(result?.months ?? [], people.data?.[0]?.birth_date ?? null),
    [result?.months, people.data],
  );

  // Sequential mode's named-failure readout: the claim no other mode can make, because
  // only here does a run correspond to a real calendar year.
  const failed = useMemo(
    () => (result?.start_years ? failedStartYears(result.fire.fi_dates, result.start_years) : null),
    [result],
  );

  // biome-ignore lint/correctness/useExhaustiveDependencies: t is stable per locale, so locale substitutes for it in deps
  useEffect(() => {
    setSlot({
      label: t("plan.headline.success"),
      value: result ? formatPercent(result.success_probability) : "—",
    });
  }, [result, locale]);

  const handleRun = () => {
    const trimmed = seedText.trim();
    const parsed = trimmed === "" ? undefined : Number(trimmed);
    const seed = parsed !== undefined && Number.isFinite(parsed) ? parsed : undefined;
    mutation.mutate(
      { ...plan.deferredRequest, n_runs: sequential ? undefined : nRuns, seed, mode },
      { onSuccess: (data) => setSeedText(data.seed === null ? "" : String(data.seed)) },
    );
  };

  const caption =
    result && bands
      ? t("plan.onzekerheid.fan.caption")
          .replace("{median}", formatEuros(bands.p50.at(-1) ?? 0))
          .replace("{month}", result.months.at(-1) ?? "")
          .replace("{p10}", formatEuros(bands.p10.at(-1) ?? 0))
          .replace("{p90}", formatEuros(bands.p90.at(-1) ?? 0))
      : "";

  return (
    <div className="space-y-6 px-4 sm:px-8">
      {mutation.isError && (
        <p role="alert" className="text-brick text-sm">
          {t("plan.onzekerheid.error")} {(mutation.error as Error).message}
        </p>
      )}

      {result && bands ? (
        <section aria-labelledby="mc-fan-heading">
          <h2
            id="mc-fan-heading"
            className="text-ink-navy/70 dark:text-paper/60 text-sm tracking-wide uppercase"
          >
            {t("plan.onzekerheid.fan.heading")}
          </h2>
          {/* THE BEAM itself, not a second drawing of the same cone in Recharts. The
              curve is p50, so the dark line and the beam's median are one line — there
              is no composition on this lens and nothing else it could be. */}
          <TimelineChart
            months={result.months}
            netWorth={bands.p50}
            components={{}}
            band={bands}
            markers={[]}
            ticks={ticks}
            selectedId={null}
            onSelect={() => {}}
            caption={caption}
          />
          <div className="mt-2 flex justify-end">
            <CsvButton
              filename="onzekerheid-banden.csv"
              columns={[
                { header: "month", values: result.months },
                { header: "p10_eur", values: result.bands.p10.map((v) => Math.round(v)) },
                { header: "p50_eur", values: result.bands.p50.map((v) => Math.round(v)) },
                { header: "p90_eur", values: result.bands.p90.map((v) => Math.round(v)) },
              ]}
            />
          </div>
          <p className="text-ink-navy/70 dark:text-paper/70 mt-2 max-w-prose text-sm">{caption}</p>
          {isPreview && (
            <p className="text-ink-navy/70 dark:text-paper/50 mt-1 max-w-prose text-xs">
              {t("plan.onzekerheid.preview").replace("{runs}", String(result.n_runs))}
            </p>
          )}
        </section>
      ) : (
        !mutation.isPending && (
          <p className="text-ink-navy/70 dark:text-paper/60 text-sm">
            {t("plan.onzekerheid.idle")}
          </p>
        )
      )}

      {result?.start_years && failed && (
        <section>
          <h3 className="text-ink-navy/70 dark:text-paper/60 text-sm tracking-wide uppercase">
            {t("plan.onzekerheid.sequential.heading")}
          </h3>
          <p className="text-ink-navy/70 dark:text-paper/70 mt-1 max-w-prose text-sm">
            {failed.length === 0
              ? t("plan.onzekerheid.sequential.allWork")
                  .replace("{first}", String(result.start_years[0]))
                  .replace("{last}", String(result.start_years.at(-1)))
              : t("plan.onzekerheid.sequential.someFail")
                  .replace("{count}", String(failed.length))
                  .replace("{total}", String(result.start_years.length))
                  .replace("{years}", failed.join(", "))}
          </p>
          <p className="text-ink-navy/70 dark:text-paper/50 mt-1 max-w-prose text-xs">
            {/* replaceAll, not replace: {n} appears twice in this string. */}
            {t("plan.onzekerheid.sequential.caveat").replaceAll(
              "{n}",
              String(result.start_years.length),
            )}
          </p>
        </section>
      )}

      {result && <FireDateHistogram fiDates={result.fire.fi_dates} />}

      {result && (
        <OutcomesPanel
          months={result.months}
          solventFraction={result.solvent_fraction}
          survival={result.survival}
        />
      )}

      <Deck
        plan={plan}
        extra={[
          {
            value: "instellingen",
            label: t("plan.deck.settings"),
            content: (
              <section
                aria-labelledby="mc-controls-heading"
                className="flex flex-wrap items-end gap-6 p-4 sm:p-8"
              >
                <h2 id="mc-controls-heading" className="sr-only">
                  {t("plan.onzekerheid.controlsHeading")}
                </h2>

                <div>
                  <label
                    htmlFor="mc-runs"
                    className="text-ink-navy/70 dark:text-paper/60 block text-xs tracking-wide uppercase"
                  >
                    {t("plan.onzekerheid.runs")}
                  </label>
                  <select
                    id="mc-runs"
                    value={nRuns}
                    disabled={sequential}
                    onChange={(e) => setNRuns(Number(e.target.value))}
                    className="border-input mt-1 rounded border bg-transparent px-2 py-1 text-sm disabled:opacity-50"
                  >
                    {RUN_OPTIONS.map((n) => (
                      <option key={n} value={n}>
                        {n.toLocaleString(locale === "nl" ? "nl-NL" : "en-US")}
                      </option>
                    ))}
                  </select>
                </div>

                <div>
                  <label
                    htmlFor="mc-seed"
                    className="text-ink-navy/70 dark:text-paper/60 block text-xs tracking-wide uppercase"
                  >
                    {t("plan.onzekerheid.seed")}
                  </label>
                  <div className="mt-1 flex items-center gap-2">
                    <Input
                      id="mc-seed"
                      type="text"
                      inputMode="numeric"
                      value={seedText}
                      disabled={sequential}
                      onChange={(e) => setSeedText(e.target.value)}
                      placeholder={t("plan.onzekerheid.seedPlaceholder")}
                      className="w-32 text-sm tabular-nums"
                    />
                    <Button
                      type="button"
                      disabled={sequential}
                      onClick={() =>
                        setSeedText(String(crypto.getRandomValues(new Uint32Array(1))[0]))
                      }
                      variant="outline"
                      size="sm"
                    >
                      {t("plan.onzekerheid.newSeed")}
                    </Button>
                  </div>
                </div>

                <fieldset>
                  <legend className="text-ink-navy/70 dark:text-paper/60 text-xs tracking-wide uppercase">
                    {t("plan.onzekerheid.model")}
                  </legend>
                  <div className="mt-1 flex flex-wrap items-center gap-4 text-sm">
                    <label className="flex items-center gap-1 py-2">
                      <input
                        type="radio"
                        name="mc-mode"
                        className="size-4 accent-ink-navy dark:accent-paper"
                        value="gaussian"
                        checked={mode === "gaussian"}
                        onChange={() => setMode("gaussian")}
                      />{" "}
                      {t("plan.onzekerheid.model.gaussian")}
                    </label>
                    <label className="flex items-center gap-1 py-2">
                      <input
                        type="radio"
                        name="mc-mode"
                        className="size-4 accent-ink-navy dark:accent-paper"
                        value="historical"
                        checked={mode === "historical"}
                        onChange={() => setMode("historical")}
                      />{" "}
                      {t("plan.onzekerheid.model.historical")}
                    </label>
                    <label className="flex items-center gap-1 py-2">
                      <input
                        type="radio"
                        name="mc-mode"
                        className="size-4 accent-ink-navy dark:accent-paper"
                        value="sequential"
                        checked={mode === "sequential"}
                        onChange={() => setMode("sequential")}
                      />{" "}
                      {t("plan.onzekerheid.model.sequential")}
                    </label>
                  </div>
                  <p className="text-ink-navy/70 dark:text-paper/50 mt-1 text-xs">
                    {t("plan.onzekerheid.model.explainer")}
                  </p>
                  {/* Under the mode that causes it, not under the controls it greys out:
                      the row is items-end, so a note inside the seed group knocks the
                      run-count select out of alignment with it. */}
                  {sequential && (
                    <p className="text-ink-navy/70 dark:text-paper/50 mt-1 text-xs">
                      {t("plan.onzekerheid.sequential.fixedRuns")}
                    </p>
                  )}
                </fieldset>

                <Button
                  type="button"
                  onClick={handleRun}
                  disabled={mutation.isPending}
                  variant="emphasis"
                >
                  {mutation.isPending ? t("plan.onzekerheid.running") : t("plan.onzekerheid.run")}
                </Button>
              </section>
            ),
          },
        ]}
      />
    </div>
  );
}
