/** "Oplossen": solve for the monthly spending/contribution that hits a goal, by bisecting
 * the pure projection. It answers the question
 * the projection sliders are used to answer by hand today. Behind a Run button — each solve
 * is many projections. */
import { useState } from "react";
import {
  CartesianGrid,
  Line,
  LineChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { type SolveGoal, type SolveKnob, useSolve, useSweep } from "../../lib/api";
import { SERIES } from "../../lib/chartColors";
import { useT } from "../../lib/i18n";
import { formatEuros, formatEuroTick, formatPercent } from "../../lib/money";
import type { usePlanState } from "../../lib/usePlanState";
import { PYODIDE } from "../../pyodide/flag";
import { ChartFigure } from "../ChartFigure";

type GoalKind = "fire_by" | "die_with_zero" | "success";

const DEFAULT_YEAR = new Date().getFullYear() + 15;

// The server's sweep default (25 points × 500 runs) takes about 4 s natively and several
// times that in single-threaded wasm, so the browser build asks for a coarser curve.
const BROWSER_SWEEP = PYODIDE ? { points: 12, n_runs: 300 } : {};

/** `floor` is the plan's bequest floor: the success goal counts it as the Uncertainty
 * lens does. */
function buildGoal(kind: GoalKind, year: number, pct: number, floor?: number): SolveGoal {
  if (kind === "fire_by") return { type: "fire_by", year };
  if (kind === "die_with_zero") return { type: "net_worth_at", year, at_least: 0 };
  return {
    type: "success_at_least",
    probability: pct / 100,
    n_runs: 1000,
    ...(floor !== undefined && { min_end_net_worth: floor }),
  };
}

export function SolvePanel({ plan }: { plan: ReturnType<typeof usePlanState> }) {
  const t = useT();
  const [knob, setKnob] = useState<SolveKnob>("monthly_spending");
  const [goalKind, setGoalKind] = useState<GoalKind>("die_with_zero");
  const [year, setYear] = useState(DEFAULT_YEAR);
  const [pct, setPct] = useState(90);
  const mutation = useSolve();
  const result = mutation.data;
  const sweepMutation = useSweep();
  const sweep = sweepMutation.data;

  const handleSolve = () => {
    mutation.mutate({
      ...plan.analysisBase,
      knob,
      goal: buildGoal(goalKind, year, pct, plan.floor),
    });
  };

  const handleSweep = () => {
    sweepMutation.mutate({ ...plan.analysisBase, knob, ...BROWSER_SWEEP });
  };

  const sweepRows = (sweep?.points ?? []).map((p) => ({
    monthly: Math.round(p.monthly),
    success: p.success,
  }));

  const knobLabel = t(
    knob === "monthly_spending" ? "plan.solve.knob.spending" : "plan.solve.knob.contributions",
  );

  return (
    <section aria-labelledby="solve-heading" className="space-y-4 p-4 sm:p-8">
      <h2
        id="solve-heading"
        className="text-sm uppercase tracking-wide text-ink-navy/70 dark:text-paper/60"
      >
        {t("plan.solve.heading")}
      </h2>

      <div className="flex flex-wrap items-end gap-6">
        <label className="block text-sm">
          <span className="block text-xs uppercase tracking-wide text-ink-navy/70 dark:text-paper/60">
            {t("plan.solve.knob")}
          </span>
          <select
            value={knob}
            onChange={(e) => setKnob(e.target.value as SolveKnob)}
            className="mt-1 rounded border border-input bg-transparent px-2 py-1"
          >
            <option value="monthly_spending">{t("plan.solve.knob.spending")}</option>
            <option value="monthly_contributions">{t("plan.solve.knob.contributions")}</option>
          </select>
        </label>

        <label className="block text-sm">
          <span className="block text-xs uppercase tracking-wide text-ink-navy/70 dark:text-paper/60">
            {t("plan.solve.goal")}
          </span>
          <select
            value={goalKind}
            onChange={(e) => setGoalKind(e.target.value as GoalKind)}
            className="mt-1 rounded border border-input bg-transparent px-2 py-1"
          >
            <option value="die_with_zero">{t("plan.solve.goal.dieWithZero")}</option>
            <option value="fire_by">{t("plan.solve.goal.fireBy")}</option>
            <option value="success">{t("plan.solve.goal.success")}</option>
          </select>
        </label>

        {goalKind === "success" ? (
          <label htmlFor="solve-probability" className="block text-sm">
            <span className="block text-xs uppercase tracking-wide text-ink-navy/70 dark:text-paper/60">
              {t("plan.solve.probability")}
            </span>
            <Input
              id="solve-probability"
              type="number"
              min={1}
              max={99}
              value={pct}
              onChange={(e) => setPct(Number(e.target.value))}
              className="mt-1 w-24 tabular-nums"
            />
          </label>
        ) : (
          <label htmlFor="solve-year" className="block text-sm">
            <span className="block text-xs uppercase tracking-wide text-ink-navy/70 dark:text-paper/60">
              {t("plan.solve.year")}
            </span>
            <Input
              id="solve-year"
              type="number"
              min={new Date().getFullYear()}
              value={year}
              onChange={(e) => setYear(Number(e.target.value))}
              className="mt-1 w-24 tabular-nums"
            />
          </label>
        )}

        <Button
          type="button"
          onClick={handleSolve}
          disabled={mutation.isPending}
          variant="emphasis"
        >
          {mutation.isPending ? t("plan.solve.running") : t("plan.solve.run")}
        </Button>
      </div>

      {mutation.isError && (
        <p role="alert" className="text-sm text-brick">
          {t("plan.solve.error")} {(mutation.error as Error).message}
        </p>
      )}

      {result &&
        (result.converged && result.solved_monthly != null ? (
          <p className="max-w-prose text-sm">
            <span className="font-display text-lg tabular-nums">
              {formatEuros(result.solved_monthly)}
            </span>{" "}
            {t("plan.solve.result.perMonth").replace("{knob}", knobLabel.toLowerCase())}{" "}
            <span className="text-ink-navy/70 dark:text-paper/60">
              {t("plan.solve.result.baseline").replace(
                "{baseline}",
                formatEuros(result.baseline_monthly),
              )}
            </span>
          </p>
        ) : (
          <p className="max-w-prose text-sm text-ink-navy/70 dark:text-paper/70">
            {t("plan.solve.result.none")}
          </p>
        ))}

      <div className="border-t border-ink-navy/10 pt-4 dark:border-paper/10">
        <div className="flex flex-wrap items-center gap-3">
          <Button
            type="button"
            onClick={handleSweep}
            disabled={sweepMutation.isPending}
            variant="outline"
          >
            {sweepMutation.isPending ? t("plan.sweep.running") : t("plan.sweep.run")}
          </Button>
          <span className="text-xs text-ink-navy/70 dark:text-paper/60">
            {t("plan.sweep.hint").replace("{knob}", knobLabel.toLowerCase())}
          </span>
        </div>

        {sweepRows.length > 0 && (
          <ChartFigure
            label={t("plan.headline.success")}
            summary={[
              `${t("chart.start")} ${formatEuros(sweepRows[0].monthly)} ${formatPercent(sweepRows[0].success)}`,
              `${t("chart.end")} ${formatEuros(sweepRows[sweepRows.length - 1].monthly)} ${formatPercent(sweepRows[sweepRows.length - 1].success)}`,
            ].join(" · ")}
            className="mt-3 h-56 w-full"
          >
            <ResponsiveContainer width="100%" height="100%">
              <LineChart data={sweepRows} margin={{ top: 8, right: 8, left: 0, bottom: 8 }}>
                <CartesianGrid strokeOpacity={0.1} vertical={false} />
                <XAxis
                  dataKey="monthly"
                  type="number"
                  domain={["dataMin", "dataMax"]}
                  tick={{ fontSize: 12 }}
                  stroke="currentColor"
                  tickFormatter={formatEuroTick}
                />
                <YAxis
                  tick={{ fontSize: 12 }}
                  stroke="currentColor"
                  width={48}
                  domain={[0, 1]}
                  tickFormatter={(v: number) => formatPercent(v)}
                />
                <Tooltip
                  formatter={(value) =>
                    typeof value === "number" ? formatPercent(value) : String(value)
                  }
                  labelFormatter={(label) =>
                    typeof label === "number" ? formatEuros(label) : String(label)
                  }
                />
                <Line
                  dataKey="success"
                  name={t("plan.headline.success")}
                  stroke={SERIES.investments}
                  strokeWidth={2}
                  dot={false}
                  isAnimationActive={false}
                />
              </LineChart>
            </ResponsiveContainer>
          </ChartFigure>
        )}
      </div>
    </section>
  );
}
