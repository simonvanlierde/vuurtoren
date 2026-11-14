import { useState } from "react";
import { Button } from "@/components/ui/button";
import { type PlanRequestBody, type TaxExplanation, useTaxExplanation } from "../../lib/api";
import { type MsgKey, useLocale, useT } from "../../lib/i18n";
import { formatMoney, formatPercent } from "../../lib/money";
import { formatTaxValue } from "../../lib/taxFields";
import { StatusChip } from "./TaxPanel";

export function TaxExplanationDetails({ data }: { data: TaxExplanation }) {
  const t = useT();
  const [locale] = useLocale();
  return (
    <div className="space-y-4">
      <p className="max-w-prose text-sm">{t("plan.checkTax.disclaimer")}</p>
      <p className="max-w-prose text-sm">
        {t("plan.checkTax.scope").replace("{start}", data.first_month)}
      </p>
      <p className="text-sm">
        {t(data.fiscal_partners ? "plan.checkTax.partners" : "plan.checkTax.individual")}
      </p>
      <dl className="grid gap-2 text-sm">
        {Object.entries(data.totals).map(([key, value]) => (
          <div key={key} className="flex flex-wrap justify-between gap-2">
            <dt>{t(`plan.checkTax.total.${key}` as MsgKey)}</dt>
            <dd className="font-mono tabular-nums">{formatMoney(value)}</dd>
          </div>
        ))}
      </dl>
      {data.calculations.map((calculation) => (
        <section key={`${calculation.label}-${calculation.person_id}`} className="space-y-2">
          <h4 className="font-medium">
            {calculation.label}
            {calculation.person_id !== null &&
              ` · ${t("plan.checkTax.person")} ${calculation.person_id}`}
          </h4>
          <ol className="space-y-2">
            {calculation.steps.map((step) => (
              <li
                key={step.rule}
                className="rounded border border-ink-navy/10 p-3 dark:border-paper/10"
              >
                <div className="flex flex-wrap justify-between gap-2 text-sm">
                  <span>{step.rule}</span>
                  <span className="font-mono tabular-nums">
                    {step.unit === "currency"
                      ? formatMoney(step.value)
                      : step.unit === "rate"
                        ? formatPercent(Number(step.value))
                        : step.value}
                  </span>
                </div>
                <ul className="mt-2 space-y-2 text-xs">
                  {Object.entries(step.parameters).map(([name, field]) => (
                    <li key={name} className="flex flex-wrap items-baseline gap-x-2 gap-y-1">
                      <span>
                        {t(`plan.tax.label.${name}` as MsgKey)}:{" "}
                        {formatTaxValue(field.value, field.unit, "EUR")}
                      </span>
                      <StatusChip status={field.status} />
                      {field.sources.map((source, index) => (
                        <a
                          key={source}
                          href={source}
                          target="_blank"
                          rel="noreferrer"
                          className="underline break-all"
                          aria-label={
                            t("plan.tax.sourceAria")
                              .replace("{field}", step.rule)
                              .replace("{domain}", new URL(source).hostname)
                              .replace("{date}", field.verified_on) +
                            (field.sources.length > 1
                              ? ` (${index + 1}/${field.sources.length})`
                              : "")
                          }
                        >
                          {new URL(source).hostname.replace(/^www\./, "")}
                          {field.sources.length > 1 && ` (${index + 1}/${field.sources.length})`}
                        </a>
                      ))}
                      <span>{t("plan.tax.verified").replace("{date}", field.verified_on)}</span>
                      <span>
                        {t(
                          field.unit === "currency" ? "plan.tax.moneyYear" : "plan.tax.sourceYear",
                        ).replace("{year}", String(field.source_year))}
                      </span>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
          </ol>
        </section>
      ))}
      <details>
        <summary className="cursor-pointer text-sm underline">{t("plan.checkTax.limits")}</summary>
        <ul className="mt-2 list-disc space-y-2 pl-5 text-sm">
          {data.limitations.map((limit) => (
            <li key={limit.en}>{limit[locale]}</li>
          ))}
        </ul>
      </details>
    </div>
  );
}

function Calculation({ request, year }: { request: PlanRequestBody; year: number }) {
  const t = useT();
  const result = useTaxExplanation(request, year);
  if (result.error)
    return (
      <p role="alert" className="text-sm">
        {t("plan.checkTax.error")} {result.error.message}
      </p>
    );
  if (!result.data)
    return (
      <p role="status" className="text-sm">
        {t("plan.opbouw.loading")}
      </p>
    );
  return <TaxExplanationDetails data={result.data} />;
}

export function TaxExplanationPanel({
  request,
  years,
}: {
  request: PlanRequestBody;
  years: number[];
}) {
  const t = useT();
  const [open, setOpen] = useState(false);
  const [selected, setSelected] = useState(years[0]);
  const year = years.includes(selected) ? selected : years[0];
  if (!years.length) return null;
  return (
    <div className="space-y-3 border-t border-ink-navy/10 pt-3 dark:border-paper/10">
      <Button
        variant="outline"
        type="button"
        aria-expanded={open}
        aria-controls="check-tax-calculation"
        onClick={() => setOpen(!open)}
      >
        {t("plan.checkTax.heading")}
      </Button>
      <div id="check-tax-calculation" hidden={!open} className="space-y-4">
        {open && (
          <>
            <label className="flex items-center gap-2 text-sm" htmlFor="check-tax-year">
              {t("plan.tax.year")}
              <select
                id="check-tax-year"
                value={year}
                onChange={(event) => setSelected(Number(event.target.value))}
                className="rounded border border-input bg-background px-3 py-2"
              >
                {years.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>
            <Calculation request={request} year={year} />
          </>
        )}
      </div>
    </div>
  );
}
