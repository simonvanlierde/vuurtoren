/** Create/edit drawer for an account. For fetched-price accounts the
 * identifier is the literal Yahoo symbol — labeled "ticker (Yahoo)", never "ISIN":
 * the first real-data run 404'd on exactly that confusion. */
import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  type Account,
  type AccountIn,
  type AccountKind,
  accountApi,
  CURRENCIES,
  type Currency,
  domicileDefault,
  OVERLAY_TREATMENTS,
  type Person,
  type PriceSource,
  useTaxConfig,
} from "../../lib/api";
import { NO_ERRORS, parseApiError } from "../../lib/fieldErrors";
import { type MsgKey, useT } from "../../lib/i18n";
import { EditorDrawer } from "./EditorDrawer";
import { DateField, DecimalField, NumberField, SelectField, TextField } from "./fields";

const KINDS: AccountKind[] = ["cash", "equity", "bond", "real_estate", "pension", "debt"];

/** The regime's vocabulary, plus whatever the account already carries. A household that
 * moved to another country keeps its old strings until each account is edited, and
 * dropping the current value from the list would rewrite it on the next save. Country-
 * scoped strings are names, not translatable copy — verbatim in both locales. */
// A person reads "Box 3 · spaargeld", not the stored key `nl.box3_bank`. The box and
// country prefixes are names and stay as they are in both locales.
const TREATMENT_LABELS: Record<string, [string, MsgKey]> = {
  "nl.box3_bank": ["Box 3", "treatment.bank"],
  "nl.box3_investment": ["Box 3", "treatment.investment"],
  "nl.box3_debt": ["Box 3", "treatment.debt"],
  "nl.box1_home": ["Box 1", "treatment.home"],
  "nl.box1_pension": ["Box 1", "treatment.pension"],
  "nl.none": ["NL", "treatment.none"],
  "at.bank": ["AT", "treatment.bank"],
  "at.investment": ["AT", "treatment.investment"],
  "at.investment_nonreporting": ["AT", "treatment.investmentNonreporting"],
  "at.debt": ["AT", "treatment.debt"],
  "at.home": ["AT", "treatment.home"],
  "at.pension": ["AT", "treatment.pension"],
  "at.none": ["AT", "treatment.none"],
};

/** Falls back to the key itself for a treatment a newer regime added. */
export function treatmentLabel(key: string, t: (k: MsgKey) => string): string {
  const entry = TREATMENT_LABELS[key];
  return entry ? `${entry[0]} · ${t(entry[1])}` : key;
}

export function treatmentOptions(current: string, valid: readonly string[]): string[] {
  return current !== "" && !valid.includes(current) ? [current, ...valid] : [...valid];
}

interface Draft {
  name: string;
  kind: AccountKind;
  tax_treatment: string;
  overlay_treatment: string;
  owner: string; // person id as string; "" = household-level
  price_source: PriceSource;
  isin: string;
  currency: Currency;
  units: string;
  manual_value: string;
  cost_basis: string;
  return_pct: string;
  volatility_pct: string;
  expense_ratio_pct: string;
  distribution_yield_pct: string;
  fund_realized_gain_pct: string;
  liquid_from: string;
}

/** A new account starts with no treatment. Defaulting to the regime's first sorted
 * string made a brokerage account be born as `nl.box1_home`, and while the tax-config
 * query was still in flight there was no first string at all, so the drawer POSTed `""`
 * — which the API rejects. The picker opens on "— choose —" and `required` blocks the
 * save until someone answers. */
export function toDraft(a: Account | null): Draft {
  return {
    name: a?.name ?? "",
    kind: a?.kind ?? "cash",
    tax_treatment: a?.tax_treatment ?? "",
    overlay_treatment: a?.overlay_treatment ?? domicileDefault(a?.isin),
    owner: a?.owner_person_id != null ? String(a.owner_person_id) : "",
    price_source: a?.price_source ?? "manual",
    isin: a?.isin ?? "",
    currency: a?.currency ?? "EUR",
    units: a?.units ?? "",
    manual_value: a?.manual_value ?? "",
    cost_basis: a?.cost_basis ?? "",
    return_pct: a ? String(Number((a.return_assumption * 100).toFixed(6))) : "0",
    volatility_pct: a ? String(Number((a.volatility_assumption * 100).toFixed(6))) : "0",
    expense_ratio_pct: a ? String(Number((a.expense_ratio * 100).toFixed(6))) : "0",
    distribution_yield_pct: a ? String(Number((a.distribution_yield * 100).toFixed(6))) : "0",
    fund_realized_gain_pct: a ? String(Number((a.fund_realized_gain_yield * 100).toFixed(6))) : "0",
    liquid_from: a?.liquid_from ?? "",
  };
}

function toBody(d: Draft, householdId: number): AccountIn {
  return {
    household_id: householdId,
    name: d.name,
    kind: d.kind,
    tax_treatment: d.tax_treatment,
    overlay_treatment: d.overlay_treatment === "" ? null : d.overlay_treatment,
    owner_person_id: d.owner === "" ? null : Number(d.owner),
    price_source: d.price_source,
    isin: d.isin.trim() === "" ? null : d.isin.trim(),
    currency: d.currency,
    units: d.units === "" ? null : d.units,
    manual_value: d.manual_value === "" ? null : d.manual_value,
    cost_basis: d.cost_basis === "" ? null : d.cost_basis,
    // return/volatility are float fields in the schema — percent → fraction float math is fine here
    return_assumption: Number(d.return_pct) / 100,
    volatility_assumption: Number(d.volatility_pct) / 100,
    expense_ratio: Number(d.expense_ratio_pct) / 100,
    distribution_yield: Number(d.distribution_yield_pct) / 100,
    fund_realized_gain_yield: Number(d.fund_realized_gain_pct) / 100,
    liquid_from: d.liquid_from === "" ? null : d.liquid_from,
  };
}

export function AccountDrawer({
  open,
  onOpenChange,
  account,
  householdId,
  taxCountry,
  people,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  account: Account | null;
  householdId: number;
  taxCountry: string;
  people: Person[];
}) {
  const t = useT();
  const [draft, setDraft] = useState<Draft>(() => toDraft(account));
  const create = accountApi.useCreate();
  const update = accountApi.useUpdate();
  const remove = accountApi.useDelete();
  const taxConfig = useTaxConfig(taxCountry, new Date().getFullYear());
  const active = account ? update : create;
  const errors = active.isError
    ? parseApiError(active.error)
    : remove.isError
      ? parseApiError(remove.error)
      : NO_ERRORS;

  function set<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((d) => ({ ...d, [key]: value }));
  }

  function save(andAnother = false) {
    const body = toBody(draft, householdId);
    const opts = {
      onSuccess: () => (andAnother ? setDraft(toDraft(null)) : onOpenChange(false)),
    };
    if (account) update.mutate({ id: account.id, body }, opts);
    else create.mutate(body, opts);
  }

  const fetched = draft.price_source === "stooq"; // stored "fetched quote" marker; UI says Yahoo

  return (
    <EditorDrawer
      open={open}
      onOpenChange={onOpenChange}
      title={account ? t("editor.account.editTitle") : t("editor.account.newTitle")}
      saving={active.isPending}
      error={errors.general}
      onSubmit={() => save()}
      onDelete={
        account
          ? () => remove.mutate(account.id, { onSuccess: () => onOpenChange(false) })
          : undefined
      }
      submitExtra={
        account ? undefined : (
          <Button
            type="button"
            onClick={() => save(true)}
            disabled={create.isPending}
            variant="outline"
          >
            {t("editor.saveAndAnother")}
          </Button>
        )
      }
    >
      <TextField
        label={t("editor.account.name")}
        value={draft.name}
        onChange={(v) => set("name", v)}
        required
        autoFocus
        error={errors.fields.name}
      />
      <SelectField
        label={t("editor.account.kind")}
        value={draft.kind}
        onChange={(v) => set("kind", v as AccountKind)}
        options={KINDS.map((k) => ({ value: k, label: t(`today.kind.${k}`) }))}
        error={errors.fields.kind}
      />
      <SelectField
        label={t("editor.account.treatment")}
        value={draft.tax_treatment}
        onChange={(v) => set("tax_treatment", v)}
        options={treatmentOptions(draft.tax_treatment, taxConfig.data?.valid_treatments ?? []).map(
          (v) => ({ value: v, label: treatmentLabel(v, t) }),
        )}
        // `required` on an empty value is what stops the save — the drawer's own
        // checkValidity reports it, so a pending tax-config query can never POST `""`.
        emptyLabel={t("editor.account.treatmentChoose")}
        required
        error={errors.fields.tax_treatment}
      />
      {/* Only for a household that has one. Three orthogonal classifications on an account
          is already a lot to hold; showing the citizenship one to everybody would make it
          look like a fourth kind of Dutch tax. */}
      {people.some((p) => p.us_person) && (
        <SelectField
          label={t("editor.account.overlayTreatment")}
          value={draft.overlay_treatment}
          onChange={(v) => set("overlay_treatment", v)}
          options={OVERLAY_TREATMENTS.map((v) => ({ value: v, label: v }))}
          emptyLabel={t("editor.account.overlayNone")}
          hint={t("editor.account.overlayHint")}
          error={errors.fields.overlay_treatment}
        />
      )}
      <SelectField
        label={t("editor.account.owner")}
        value={draft.owner}
        onChange={(v) => set("owner", v)}
        options={people.map((p) => ({ value: String(p.id), label: p.name }))}
        emptyLabel={t("editor.account.household")}
        error={errors.fields.owner_person_id}
      />
      <SelectField
        label={t("editor.account.priceSource")}
        value={draft.price_source}
        onChange={(v) => set("price_source", v as PriceSource)}
        options={[
          { value: "manual", label: t("editor.account.priceManual") },
          { value: "stooq", label: t("editor.account.priceFetched") },
        ]}
        error={errors.fields.price_source}
      />
      {fetched ? (
        <>
          <TextField
            label={t("editor.account.ticker")}
            value={draft.isin}
            onChange={(v) => set("isin", v)}
            placeholder="VT"
            hint={t("editor.account.tickerHint")}
            error={errors.fields.isin}
          />
          <SelectField
            label={t("editor.account.currency")}
            value={draft.currency}
            onChange={(v) => set("currency", v as Currency)}
            options={CURRENCIES.map((c) => ({ value: c, label: c }))}
            hint={t("editor.account.currencyHint")}
            error={errors.fields.currency}
          />
          <DecimalField
            label={t("editor.account.units")}
            value={draft.units}
            onChange={(v) => set("units", v)}
            error={errors.fields.units}
          />
        </>
      ) : (
        <DecimalField
          label={t("editor.account.manualValue")}
          value={draft.manual_value}
          onChange={(v) => set("manual_value", v)}
          error={errors.fields.manual_value}
        />
      )}
      <DecimalField
        label={t("editor.account.costBasis")}
        value={draft.cost_basis}
        onChange={(v) => set("cost_basis", v)}
        error={errors.fields.cost_basis}
      />
      <NumberField
        label={t("editor.account.returnPct")}
        value={draft.return_pct}
        onChange={(v) => set("return_pct", v)}
        step="0.1"
        error={errors.fields.return_assumption}
      />
      <NumberField
        label={t("editor.account.volatilityPct")}
        value={draft.volatility_pct}
        onChange={(v) => set("volatility_pct", v)}
        step="0.1"
        error={errors.fields.volatility_assumption}
      />
      <NumberField
        label={t("editor.account.expenseRatioPct")}
        value={draft.expense_ratio_pct}
        onChange={(v) => set("expense_ratio_pct", v)}
        step="0.01"
        hint={t("editor.account.expenseRatioHint")}
        error={errors.fields.expense_ratio}
      />
      <NumberField
        label={t("editor.account.distributionYieldPct")}
        value={draft.distribution_yield_pct}
        onChange={(v) => set("distribution_yield_pct", v)}
        step="0.01"
        hint={t("editor.account.distributionYieldHint")}
        error={errors.fields.distribution_yield}
      />
      <NumberField
        label={t("editor.account.fundRealizedGainPct")}
        value={draft.fund_realized_gain_pct}
        onChange={(v) => set("fund_realized_gain_pct", v)}
        step="0.1"
        hint={t("editor.account.fundRealizedGainHint")}
        error={errors.fields.fund_realized_gain_yield}
      />
      <DateField
        label={t("editor.account.liquidFrom")}
        value={draft.liquid_from}
        onChange={(v) => set("liquid_from", v)}
        hint={t("editor.account.liquidFromHint")}
        error={errors.fields.liquid_from}
      />
    </EditorDrawer>
  );
}
