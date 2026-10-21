/** The Plan canvas's assumption rail: the three live assumptions plus the display
 * knobs, beside the chart from `lg` up and a collapsed sticky strip below it.
 *
 * Moving an assumption and watching the beam move is the product's core loop, so the
 * sliders sit beside the chart they drive rather than a fold below it.
 */
import { useEffect, useId, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useT } from "../../lib/i18n";
import { formatPercent, parsePercentInput, percentInputText } from "../../lib/money";
import { FROM_LG, useMediaQuery } from "../../lib/useMediaQuery";
import type { usePlanState } from "../../lib/usePlanState";
import { CheckboxField, NumberField } from "../editor/fields";
import { ShareButton } from "./ShareButton";

function Assumption({
  label,
  value,
  min,
  max,
  onChange,
}: {
  label: string;
  value: number;
  min: number;
  max: number;
  onChange: (v: number) => void;
}) {
  const id = useId();
  const [text, setText] = useState(() => percentInputText(value));
  // Reformat only when the value has moved somewhere the typed text does not already
  // say: dragging the slider rewrites the box, but typing "3,50" is not snapped to "3,5"
  // under the cursor.
  useEffect(() => {
    setText((current) =>
      Math.abs((parsePercentInput(current) ?? Number.NaN) - value) < 1e-9
        ? current
        : percentInputText(value),
    );
  }, [value]);

  // Where the drag started, so a change reads as a transition rather than a silent
  // substitution. Pointer drags clear on release; a keyboard run clears on blur, so it
  // shows the whole distance travelled rather than the last arrow press.
  const [before, setBefore] = useState<number | null>(null);

  return (
    <div>
      <div className="flex items-baseline justify-between gap-2">
        <label id={`${id}-label`} htmlFor={id} className="text-sm font-medium">
          {label}
        </label>
        <span className="flex items-baseline gap-0.5 text-sm tabular-nums">
          <Input
            id={id}
            type="text"
            inputMode="decimal"
            value={text}
            onChange={(e) => {
              setText(e.target.value);
              const parsed = parsePercentInput(e.target.value);
              // Clamped to the slider's own range: the box would otherwise send a typo
              // like 50% inflation straight into the request.
              if (parsed !== null) onChange(Math.min(max, Math.max(min, parsed)));
            }}
            className="w-16 px-1 text-right text-sm"
          />
          %
        </span>
      </div>
      <input
        type="range"
        className="slider"
        aria-labelledby={`${id}-label`}
        min={min}
        max={max}
        step={0.001}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        onPointerDown={() => setBefore(value)}
        onPointerUp={() => setBefore(null)}
        onPointerCancel={() => setBefore(null)}
        onKeyDown={() => setBefore((b) => b ?? value)}
        onBlur={() => setBefore(null)}
      />
      {/* Reserved, not conditional: a line appearing mid-drag would shove the slider
          under the pointer. */}
      <p aria-live="off" className="h-4 text-xs tabular-nums text-ink-navy/70 dark:text-paper/60">
        {before !== null && before !== value
          ? `${formatPercent(before)} → ${formatPercent(value)}`
          : ""}
      </p>
    </div>
  );
}

export function AssumptionsRail({ plan }: { plan: ReturnType<typeof usePlanState> }) {
  const t = useT();
  // A `<details>` cannot be forced open by CSS, so `lg` is read as a value here rather
  // than as a class. Below it the strip is collapsed and user-toggleable.
  const wide = useMediaQuery(FROM_LG);

  return (
    <details
      open={wide || undefined}
      className="sticky top-0 z-20 order-first bg-paper px-4 lg:top-6 lg:order-last lg:w-72 lg:shrink-0 lg:pr-8 lg:pl-0 dark:bg-night-sea"
    >
      {/* The native disclosure triangle stays: it is the only cue that the strip opens. */}
      <summary className="flex min-h-11 cursor-pointer items-center gap-2 text-sm lg:hidden">
        <span className="font-medium">{t("plan.assumptions.heading")}</span>
        <span className="tabular-nums text-ink-navy/70 dark:text-paper/60">
          {[
            [t("plan.assumptions.inflation"), plan.inflation],
            [t("plan.assumptions.swr"), plan.swr],
            [t("plan.assumptions.houseShort"), plan.houseAppreciation],
          ]
            .map(([label, v]) => `${label} ${formatPercent(v as number)}`)
            .join(" · ")}
        </span>
      </summary>
      <section
        aria-labelledby="assumptions-heading"
        className="space-y-3 border-t border-ink-navy/10 pt-3 pb-4 lg:border-0 lg:pt-0 dark:border-paper/10"
      >
        <h2
          id="assumptions-heading"
          className="sr-only text-sm uppercase tracking-wide lg:not-sr-only lg:text-ink-navy/70 dark:lg:text-paper/60"
        >
          {t("plan.assumptions.heading")}
        </h2>
        <Assumption
          label={t("plan.assumptions.inflation")}
          value={plan.inflation}
          min={0}
          max={0.06}
          onChange={plan.setInflation}
        />
        <Assumption
          label={t("plan.assumptions.swr")}
          value={plan.swr}
          min={0.02}
          max={0.08}
          onChange={plan.setSwr}
        />
        <Assumption
          label={t("plan.assumptions.houseAppreciation")}
          value={plan.houseAppreciation}
          min={0}
          max={0.06}
          onChange={plan.setHouseAppreciation}
        />
        {!plan.assumptionsAreDefault && (
          <Button type="button" onClick={plan.resetAssumptions} variant="outline">
            {t("plan.assumptions.reset")}
          </Button>
        )}
        <CheckboxField
          label={t("plan.assumptions.realTerms")}
          checked={plan.realTerms}
          onChange={plan.setRealTerms}
          hint={t("plan.assumptions.realTermsHint")}
        />
        <NumberField
          label={t("plan.assumptions.bequestFloor")}
          value={plan.minEndNetWorth}
          onChange={plan.setMinEndNetWorth}
          step="10000"
          hint={t("plan.assumptions.bequestFloorHint")}
        />
        <ShareButton plan={plan} />
      </section>
    </details>
  );
}
