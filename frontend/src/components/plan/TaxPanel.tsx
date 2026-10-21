import { useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { useTaxConfig } from "../../lib/api";
import { type MsgKey, useLocale, useT } from "../../lib/i18n";
import {
  formatTaxValue,
  groupTaxFields,
  type TaxFieldRow,
  type TaxStatus,
  taxValueError,
} from "../../lib/taxFields";
import { DataTable } from "../ui/DataTable";
import { EditedBadge } from "../ui/EditedBadge";

/** The domain, not the word "Source": 31 links all announcing "Source, link" gave a screen
 * reader nothing to tell them apart, and the host is the part that carries the authority. */
function sourceDomain(url: string): string {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

export function StatusChip({ status }: { status: TaxStatus }) {
  const t = useT();
  // "final" gets a chip too: a blank cell reads as missing data on the one surface whose
  // job is to prove the figures.
  if (status === "final") {
    return (
      <span className="text-ink-navy/70 dark:text-paper/60 text-xs font-medium">
        {t("plan.tax.final")}
      </span>
    );
  }
  if (status === "user") {
    return <EditedBadge>{t("plan.tax.edited")}</EditedBadge>;
  }
  return (
    <span
      className={`rounded border px-1.5 py-0.5 text-xs font-medium text-ink-navy dark:text-paper ${
        status === "proposed"
          ? "border-dashed border-beacon-amber bg-beacon-amber/15"
          : "border-beacon-amber bg-beacon-amber/15"
      }`}
    >
      {t(`plan.tax.${status}`)}
    </span>
  );
}

/** One figure's value cell.
 *
 * Read-only until asked otherwise, so an accidental keystroke cannot break a figure's
 * provenance: overriding is a deliberate act. The value is range-checked here rather
 * than at projection time, where an out-of-range rate would surface as a failed run with
 * no field named.
 */
function ValueCell({
  row,
  currency,
  override,
  onEdit,
  onReset,
}: {
  row: TaxFieldRow;
  currency: string;
  override: string | undefined;
  onEdit: (value: string) => void;
  onReset: () => void;
}) {
  const t = useT();
  const [editing, setEditing] = useState(false);
  // What is typed, which is not what is committed: an override only reaches the request
  // once it passes the field's range, so a half-typed "0." or an out-of-range rate shows
  // its error here instead of coming back as a failed projection with no field named.
  const [typed, setTyped] = useState(override ?? row.field.value);
  const open = editing || override !== undefined;
  const errorKey = open ? taxValueError(typed, row.field.unit) : null;

  if (!open) {
    return (
      <div className="flex items-center justify-end gap-3 sm:justify-start">
        <span className="tabular-nums">
          {formatTaxValue(row.field.value, row.field.unit, currency)}
        </span>
        <Button
          type="button"
          onClick={() => setEditing(true)}
          aria-label={t("plan.tax.overrideAria").replace("{field}", row.label)}
          variant="link"
          size="xs"
          className="text-foreground/60 underline"
        >
          {t("plan.tax.override")}
        </Button>
      </div>
    );
  }

  return (
    <div className="flex flex-col items-end gap-1 sm:items-start">
      <div className="flex items-center gap-1">
        <Input
          value={typed}
          onChange={(e) => {
            setTyped(e.target.value);
            if (taxValueError(e.target.value, row.field.unit) === null) onEdit(e.target.value);
          }}
          aria-label={row.label}
          aria-invalid={errorKey !== null}
          inputMode="decimal"
          autoFocus
          className={`w-32 font-mono text-xs tabular-nums ${errorKey ? "border-brick" : ""}`}
        />
        <Button
          type="button"
          onClick={() => {
            onReset();
            setTyped(row.field.value);
            setEditing(false);
          }}
          aria-label={t("plan.tax.resetAria").replace("{field}", row.label)}
          variant="link"
          size="xs"
          className="text-foreground/60 underline"
        >
          {t("plan.tax.reset")}
        </Button>
      </div>
      {errorKey && (
        <p role="alert" className="text-xs text-brick">
          {t(errorKey as MsgKey)}
        </p>
      )}
    </div>
  );
}

export function TaxPanel({
  country,
  taxYear,
  setTaxYear,
  overrides,
  editField,
  resetField,
}: {
  country: string | undefined;
  taxYear: number;
  setTaxYear: (y: number) => void;
  overrides: Record<number, Record<string, string>>;
  editField: (name: string, value: string) => void;
  resetField: (name: string) => void;
}) {
  const t = useT();
  const [locale] = useLocale();
  const taxConfig = useTaxConfig(country, taxYear);

  const groups = useMemo(
    () => (taxConfig.data ? groupTaxFields(taxConfig.data.fields, locale) : []),
    [taxConfig.data, locale],
  );

  return (
    <section aria-labelledby="tax-panel-heading">
      <div className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 id="tax-panel-heading" className="font-display text-lg">
          {t("plan.tax.heading")}
        </h2>
        <label htmlFor="tax-year" className="flex items-center gap-2 text-sm">
          <span>{t("plan.tax.year")}</span>
          <Input
            id="tax-year"
            type="number"
            className="w-24 tabular-nums"
            value={taxYear}
            onChange={(e) => setTaxYear(Number(e.target.value))}
          />
        </label>
      </div>
      {groups.map((group) => (
        <div key={group.id} className="mt-4">
          <h3 className="text-sm font-medium">{group.label}</h3>
          <DataTable
            className="mt-1"
            caption={group.label}
            rows={group.rows}
            rowKey={(row) => row.name}
            columns={[
              { header: t("plan.tax.field"), title: true, cell: (row) => row.label },
              {
                header: t("plan.tax.value"),
                cell: (row) => (
                  <ValueCell
                    key={`${row.name}-${taxYear}`}
                    row={row}
                    currency={taxConfig.data?.currency ?? "EUR"}
                    override={overrides[taxYear]?.[row.name]}
                    onEdit={(value) => editField(row.name, value)}
                    onReset={() => resetField(row.name)}
                  />
                ),
              },
              {
                header: t("plan.tax.status"),
                cell: (row) => {
                  const override = overrides[taxYear]?.[row.name];
                  const status: TaxStatus = override !== undefined ? "user" : row.field.status;
                  return <StatusChip status={status} />;
                },
              },
              {
                header: t("plan.tax.source"),
                cell: (row) => {
                  const domain = sourceDomain(row.field.source);
                  return (
                    <div className="flex flex-col items-end gap-0.5 sm:items-start">
                      <a
                        href={row.field.source}
                        target="_blank"
                        rel="noreferrer"
                        aria-label={t("plan.tax.sourceAria")
                          .replace("{field}", row.label)
                          .replace("{domain}", domain)
                          .replace("{date}", row.field.verified_on)}
                        className="font-mono text-xs underline"
                      >
                        {domain}
                      </a>
                      {/* The verification date is half the product's positioning and was
                          computed, typed and shipped to the client — just never drawn. */}
                      <span className="text-ink-navy/70 dark:text-paper/50 text-xs tabular-nums">
                        {t("plan.tax.verified").replace("{date}", row.field.verified_on)}
                      </span>
                    </div>
                  );
                },
              },
            ]}
          />
        </div>
      ))}
    </section>
  );
}
