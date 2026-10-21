/** FBAR / FATCA threshold worksheet, for a household that has a US person.
 *
 * A worksheet, not advice — it computes figures and states which thresholds they appear
 * to cross. The disclaimer at the foot is load-bearing, not decoration: this is the one
 * panel in the app whose output someone might copy onto a government form.
 *
 * The rate is an input rather than a fetch. Treasury has published no rate for any year
 * a projection reaches, so the panel asks for the assumption instead of pretending to
 * know it, and shows the direction (dollars per one euro is NOT what this is).
 */
import { useState } from "react";
import { type FbarWorksheet, useFbarWorksheet, usePeople } from "../../lib/api";
import { parseApiError } from "../../lib/fieldErrors";
import { useT } from "../../lib/i18n";
import type { usePlanState } from "../../lib/usePlanState";
import { CsvButton } from "./CsvButton";

const usd = (s: string) => `$${Number(s).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;
const eur = (s: string) => `€${Number(s).toLocaleString("en-US", { maximumFractionDigits: 0 })}`;

function Verdict({ triggered, label }: { triggered: boolean; label: string }) {
  const t = useT();
  return (
    <p className="text-sm">
      <span className="font-medium">{label}</span>{" "}
      {/* Never a bare colour: the state is in the words, so it survives a greyscale
          print and a screen reader alike. */}
      {triggered ? t("plan.usReport.appearsTriggered") : t("plan.usReport.appearsNotTriggered")}
    </p>
  );
}

export function Sheet({ sheet }: { sheet: FbarWorksheet }) {
  const t = useT();
  return (
    <div className="space-y-3">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h4 className="font-medium">
          {sheet.person_name}{" "}
          <span className="text-ink-navy/70 dark:text-paper/60">
            ({t(`editor.person.filing.${sheet.filing_status}`)})
          </span>
        </h4>
        <CsvButton
          filename={`fbar-${sheet.person_name}.csv`}
          columns={[
            { header: "account", values: sheet.accounts.map((a) => a.name) },
            { header: "peak_eur", values: sheet.accounts.map((a) => a.peak_local) },
            { header: "peak_usd", values: sheet.accounts.map((a) => a.peak_usd) },
            { header: "year_end_eur", values: sheet.accounts.map((a) => a.year_end_local) },
            { header: "year_end_usd", values: sheet.accounts.map((a) => a.year_end_usd) },
          ]}
        />
      </div>

      {/* Wide tables scroll inside their own box rather than pushing the page sideways. */}
      <div className="overflow-x-auto">
        <table className="w-full min-w-[32rem] text-sm tabular-nums">
          <thead className="text-left text-xs text-ink-navy/70 dark:text-paper/60">
            <tr>
              <th scope="col" className="py-1 pr-3 font-medium">
                {t("plan.usReport.account")}
              </th>
              <th scope="col" className="py-1 pr-3 text-right font-medium">
                {t("plan.usReport.peak")}
              </th>
              <th scope="col" className="py-1 pr-3 text-right font-medium">
                {t("plan.usReport.peakUsd")}
              </th>
              <th scope="col" className="py-1 text-right font-medium">
                {t("plan.usReport.yearEndUsd")}
              </th>
            </tr>
          </thead>
          <tbody>
            {sheet.accounts.map((a) => (
              <tr key={a.account_id} className="border-t border-ink-navy/10 dark:border-paper/10">
                <td className="py-1 pr-3">{a.name}</td>
                <td className="py-1 pr-3 text-right">{eur(a.peak_local)}</td>
                <td className="py-1 pr-3 text-right">{usd(a.peak_usd)}</td>
                <td className="py-1 text-right">{usd(a.year_end_usd)}</td>
              </tr>
            ))}
            <tr className="border-t border-ink-navy/20 font-medium dark:border-paper/20">
              <td className="py-1 pr-3">{t("plan.usReport.aggregate")}</td>
              <td className="py-1 pr-3" />
              <td className="py-1 pr-3 text-right">{usd(sheet.aggregate_peak_usd)}</td>
              <td className="py-1 text-right">{usd(sheet.aggregate_year_end_usd)}</td>
            </tr>
          </tbody>
        </table>
      </div>

      <Verdict
        triggered={sheet.fbar_triggered}
        label={t("plan.usReport.fbar").replace("{threshold}", usd(sheet.fbar_threshold_usd))}
      />
      <Verdict
        triggered={sheet.fatca_triggered}
        label={t("plan.usReport.fatca")
          .replace("{lastDay}", usd(sheet.fatca_last_day_threshold_usd))
          .replace("{anyTime}", usd(sheet.fatca_any_time_threshold_usd))}
      />
    </div>
  );
}

export function UsReportingPanel({ plan }: { plan: ReturnType<typeof usePlanState> }) {
  const t = useT();
  const people = usePeople();
  const hasUsPerson = (people.data ?? []).some((p) => p.us_person);
  const [year, setYear] = useState(() => new Date().getFullYear());
  const [rate, setRate] = useState("0.851");

  const report = useFbarWorksheet(plan.deferredRequest, year, rate, hasUsPerson);

  return (
    <div className="space-y-4 px-4 py-3 sm:px-8">
      <div className="flex flex-wrap items-end gap-4">
        <label className="space-y-1 text-sm">
          <span className="block font-medium">{t("plan.usReport.year")}</span>
          <input
            type="number"
            value={year}
            onChange={(e) => setYear(Number(e.target.value))}
            className="min-h-11 w-28 rounded border border-input bg-transparent px-2 text-sm tabular-nums sm:min-h-0"
          />
        </label>
        <label className="space-y-1 text-sm">
          <span className="block font-medium">{t("plan.usReport.rate")}</span>
          <input
            type="text"
            inputMode="decimal"
            value={rate}
            onChange={(e) => setRate(e.target.value)}
            className="min-h-11 w-28 rounded border border-input bg-transparent px-2 text-sm tabular-nums sm:min-h-0"
          />
          <span className="block text-xs text-ink-navy/70 dark:text-paper/60">
            {t("plan.usReport.rateHint")}
          </span>
        </label>
      </div>

      {report.isError && (
        <p role="alert" className="text-sm text-brick">
          {parseApiError(report.error).general}
        </p>
      )}
      {report.data?.worksheets.length === 0 && (
        <p className="text-sm text-ink-navy/70 dark:text-paper/70">{t("plan.usReport.nobody")}</p>
      )}
      {report.data?.worksheets.map((sheet) => (
        <Sheet key={sheet.person_id} sheet={sheet} />
      ))}

      <p className="max-w-prose border-t border-ink-navy/10 pt-3 text-xs text-ink-navy/70 dark:border-paper/10 dark:text-paper/60">
        {t("plan.usReport.disclaimer")}
      </p>
    </div>
  );
}
