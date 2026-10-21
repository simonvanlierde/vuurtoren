/** Create/edit drawer for a milestone — type picker as chips, one
 * datum/leeftijd control mirroring the API's either/or. A complete CREATE draft
 * live-previews the Plan chart via overrides.added_milestones; edits
 * save without preview — per-milestone patching is a deferred scenario group. */
import { useEffect, useMemo, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  type Milestone,
  milestoneApi,
  useAccounts,
  useCashFlows,
  usePeople,
  useTaxConfig,
  useTaxCountries,
} from "../../lib/api";
import { NO_ERRORS, parseApiError } from "../../lib/fieldErrors";
import { useT } from "../../lib/i18n";
import type { usePlanState } from "../../lib/usePlanState";
import { treatmentLabel } from "./AccountDrawer";
import { EditorDrawer } from "./EditorDrawer";
import {
  CheckboxField,
  DateField,
  DecimalField,
  NumberField,
  SelectField,
  TextField,
} from "./fields";
import {
  defaultParams,
  emptyDraft,
  fromMilestone,
  isComplete,
  MILESTONE_TYPES,
  type MilestoneDraft,
  retagKey,
  toBody,
} from "./milestoneDraft";

export function MilestoneDrawer({
  plan,
  milestone,
}: {
  plan: ReturnType<typeof usePlanState>;
  milestone: Milestone | null;
}) {
  const t = useT();
  const people = usePeople();
  const accounts = useAccounts();
  const cashFlows = useCashFlows();
  const [draft, setDraft] = useState<MilestoneDraft>(() =>
    milestone ? fromMilestone(milestone) : emptyDraft(),
  );
  const create = milestoneApi.useCreate();
  const update = milestoneApi.useUpdate();
  const remove = milestoneApi.useDelete();
  const active = milestone ? update : create;
  const errors = active.isError
    ? parseApiError(active.error)
    : remove.isError
      ? parseApiError(remove.error)
      : NO_ERRORS;
  const householdId = plan.household?.id ?? 0;
  const { setPreviewOverrides, setMilestoneEditor } = plan;

  // A move lists every account in the household, compared against its stored treatment.
  // NOTE: a second move compares against the stored tags too, not the ones an earlier
  // move set; the projection names any account that still needs one.
  const isMove = draft.type === "change_tax_residence";
  const target = isMove && draft.params.country ? String(draft.params.country) : undefined;
  const taxCountries = useTaxCountries();
  const targetConfig = useTaxConfig(target, new Date().getFullYear());
  const targetTreatments =
    target !== undefined && targetConfig.data?.country === target
      ? targetConfig.data.valid_treatments
      : null;
  const householdAccounts = (accounts.data ?? []).filter((a) => a.household_id === householdId);
  const requiredRetags =
    targetTreatments === null
      ? null
      : householdAccounts
          .filter((a) => !targetTreatments.includes(a.tax_treatment))
          .map((a) => a.id);

  function close() {
    setMilestoneEditor(null);
  }

  function set<K extends keyof MilestoneDraft>(key: K, value: MilestoneDraft[K]) {
    setDraft((d) => ({ ...d, [key]: value }));
  }

  function setParam(name: string, value: string | boolean) {
    setDraft((d) => ({ ...d, params: { ...d.params, [name]: value } }));
  }

  // Live preview, create-only: JSON string as the effect key so an unchanged
  // draft object identity never re-fires the projection.
  const previewJson = useMemo(
    () =>
      milestone == null && isComplete(draft, isMove ? requiredRetags : [])
        ? JSON.stringify({
            added_milestones: [{ id: 0, ...toBody(draft, householdId), label: "" }],
          })
        : null,
    [draft, milestone, householdId, isMove, requiredRetags],
  );
  useEffect(() => {
    setPreviewOverrides(previewJson == null ? null : JSON.parse(previewJson));
  }, [previewJson, setPreviewOverrides]);
  useEffect(() => () => setPreviewOverrides(null), [setPreviewOverrides]);

  function save() {
    const body = toBody(draft, householdId);
    if (milestone) update.mutate({ id: milestone.id, body }, { onSuccess: close });
    else create.mutate(body, { onSuccess: close });
  }

  const personOptions = (people.data ?? []).map((p) => ({ value: String(p.id), label: p.name }));
  const flowOptions = (kind: string) =>
    (cashFlows.data ?? [])
      .filter((f) => f.kind === kind)
      .map((f) => ({ value: String(f.id), label: f.label }));
  const changeKind: Record<string, string> = {
    income_change: "income",
    expense_change: "expense",
    contribution_change: "contribution",
  };

  return (
    <EditorDrawer
      open
      onOpenChange={(o) => {
        if (!o) close();
      }}
      title={milestone ? t("editor.milestone.editTitle") : t("editor.milestone.newTitle")}
      saving={active.isPending}
      error={errors.general}
      onSubmit={save}
      onDelete={milestone ? () => remove.mutate(milestone.id, { onSuccess: close }) : undefined}
    >
      <TextField
        label={t("editor.milestone.label")}
        value={draft.label}
        onChange={(v) => set("label", v)}
        required
        autoFocus
        error={errors.fields.label}
      />

      {/* type picker chips — switching keeps label + timing, resets params */}
      <fieldset>
        <legend className="text-sm font-medium">{t("editor.milestone.type")}</legend>
        <div className="mt-1 flex flex-wrap gap-2">
          {MILESTONE_TYPES.map((type) => (
            <Button
              key={type}
              type="button"
              aria-pressed={draft.type === type}
              onClick={() => setDraft((d) => ({ ...d, type, params: defaultParams(type) }))}
              // Variant, not className: a className here loses to the default variant's
              // bg-primary, which rendered all ten chips as solid primary — the selected
              // one indistinguishable from the other nine.
              variant={draft.type === type ? "default" : "outline"}
            >
              {t(`plan.milestones.type.${type}`)}
            </Button>
          ))}
        </div>
      </fieldset>

      {/* timing: one datum/leeftijd control mirroring the API's either/or */}
      <fieldset>
        <legend className="text-sm font-medium">{t("editor.milestone.timing")}</legend>
        <div className="mt-1 flex gap-2">
          {(["date", "age"] as const).map((mode) => (
            <Button
              key={mode}
              type="button"
              aria-pressed={draft.timing === mode}
              onClick={() => set("timing", mode)}
              // Same rule as the type chips above: variant, not className, or bg-primary
              // renders both modes as pressed.
              variant={draft.timing === mode ? "default" : "outline"}
            >
              {t(`editor.milestone.timing.${mode}`)}
            </Button>
          ))}
        </div>
      </fieldset>
      {draft.timing === "date" ? (
        <DateField
          label={t("editor.milestone.onDate")}
          value={draft.on_date}
          onChange={(v) => set("on_date", v)}
          required
          error={errors.fields.on_date}
        />
      ) : (
        <>
          <SelectField
            label={t("editor.milestone.agePerson")}
            value={draft.age_person}
            onChange={(v) => set("age_person", v)}
            options={personOptions}
            emptyLabel="—"
            error={errors.fields.age_person_id}
          />
          <NumberField
            label={t("editor.milestone.ageYears")}
            value={draft.age_years}
            onChange={(v) => set("age_years", v)}
            required
            error={errors.fields.age_years}
          />
        </>
      )}

      {/* per-type params */}
      {draft.type === "retire" && (
        <SelectField
          label={t("editor.milestone.person")}
          value={String(draft.params.person_id ?? "")}
          onChange={(v) => setParam("person_id", v)}
          options={personOptions}
          emptyLabel="—"
          error={errors.fields.person_id}
        />
      )}
      {(draft.type === "lump_sum_in" || draft.type === "lump_sum_out") && (
        <DecimalField
          label={t("editor.milestone.amount")}
          value={String(draft.params.amount ?? "")}
          onChange={(v) => setParam("amount", v)}
          required
          error={errors.fields.amount}
        />
      )}
      {draft.type === "lump_sum_in" && (
        <>
          <SelectField
            label={t("editor.milestone.targetAccount")}
            value={String(draft.params.target_account_id ?? "")}
            onChange={(v) => setParam("target_account_id", v)}
            options={(accounts.data ?? []).map((a) => ({ value: String(a.id), label: a.name }))}
            emptyLabel="—"
            error={errors.fields.target_account_id}
          />
          <CheckboxField
            label={t("editor.milestone.giftExemption")}
            checked={draft.params.is_gift_exemption === true}
            onChange={(v) => setParam("is_gift_exemption", v)}
          />
        </>
      )}
      {draft.type === "buy_property" && (
        <>
          <DecimalField
            label={t("editor.milestone.price")}
            value={String(draft.params.price ?? "")}
            onChange={(v) => setParam("price", v)}
            required
            error={errors.fields.price}
          />
          <DecimalField
            label={t("editor.milestone.mortgage")}
            value={String(draft.params.mortgage ?? "")}
            onChange={(v) => setParam("mortgage", v)}
            required
            error={errors.fields.mortgage}
          />
          <DecimalField
            label={t("editor.milestone.annualRate")}
            value={String(draft.params.annual_rate ?? "")}
            onChange={(v) => setParam("annual_rate", v)}
            required
            hint={t("editor.milestone.annualRateHint")}
            error={errors.fields.annual_rate}
          />
          <NumberField
            label={t("editor.milestone.termMonths")}
            value={String(draft.params.term_months ?? "")}
            onChange={(v) => setParam("term_months", v)}
            error={errors.fields.term_months}
          />
          <DecimalField
            label={t("editor.milestone.vveMonthly")}
            value={String(draft.params.vve_monthly ?? "")}
            onChange={(v) => setParam("vve_monthly", v)}
            error={errors.fields.vve_monthly}
          />
          <SelectField
            label={t("editor.milestone.buyer")}
            value={String(draft.params.buyer_person_id ?? "")}
            onChange={(v) => setParam("buyer_person_id", v)}
            options={personOptions}
            emptyLabel="—"
            error={errors.fields.buyer_person_id}
          />
          <DecimalField
            label={t("editor.milestone.giftUsed")}
            value={String(draft.params.gift_used ?? "")}
            onChange={(v) => setParam("gift_used", v)}
            error={errors.fields.gift_used}
          />
          <CheckboxField
            label={t("editor.milestone.ownOccupancy")}
            checked={draft.params.own_occupancy === true}
            onChange={(v) => setParam("own_occupancy", v)}
          />
        </>
      )}
      {draft.type === "sell_property" && (
        <DecimalField
          label={t("editor.milestone.sellCosts")}
          value={String(draft.params.costs ?? "")}
          onChange={(v) => setParam("costs", v)}
          error={errors.fields.costs}
        />
      )}
      {draft.type === "extra_repayment" && (
        <DecimalField
          label={t("editor.milestone.extraRepayment")}
          hint={t("editor.milestone.extraRepaymentHint")}
          value={String(draft.params.monthly_amount ?? "")}
          onChange={(v) => setParam("monthly_amount", v)}
          error={errors.fields.monthly_amount}
        />
      )}
      {draft.type in changeKind && (
        <>
          <SelectField
            label={t("editor.milestone.cashFlow")}
            value={String(draft.params.cash_flow_id ?? "")}
            onChange={(v) => setParam("cash_flow_id", v)}
            options={flowOptions(changeKind[draft.type])}
            emptyLabel="—"
            error={errors.fields.cash_flow_id}
          />
          <DecimalField
            label={t("editor.milestone.newAmount")}
            value={String(draft.params.new_amount_monthly ?? "")}
            onChange={(v) => setParam("new_amount_monthly", v)}
            required
            error={errors.fields.new_amount_monthly}
          />
        </>
      )}
      {draft.type === "change_tax_residence" && (
        <>
          <SelectField
            label={t("editor.milestone.country")}
            value={String(draft.params.country ?? "")}
            // A new country invalidates every treatment picked for the old one.
            onChange={(v) => setDraft((d) => ({ ...d, params: { country: v } }))}
            options={(taxCountries.data ?? []).map((c) => ({ value: c, label: c }))}
            emptyLabel={t("editor.account.treatmentChoose")}
            required
            hint={t("editor.milestone.countryHint")}
            error={errors.fields.country}
          />
          {targetTreatments !== null && householdAccounts.length > 0 && (
            <fieldset>
              <legend className="text-sm font-medium">{t("editor.milestone.retag")}</legend>
              <p className="mt-1 text-sm text-muted-foreground">
                {t("editor.milestone.retagHint").replaceAll("{country}", target ?? "")}
              </p>
              <div className="mt-4 space-y-4">
                {householdAccounts.map((a) => {
                  const required = requiredRetags?.includes(a.id) ?? false;
                  return (
                    <SelectField
                      key={a.id}
                      label={a.name}
                      value={String(draft.params[retagKey(a.id)] ?? "")}
                      onChange={(v) => setParam(retagKey(a.id), v)}
                      options={targetTreatments.map((v) => ({
                        value: v,
                        label: treatmentLabel(v, t),
                      }))}
                      emptyLabel={
                        required
                          ? t("editor.account.treatmentChoose")
                          : t("editor.milestone.retagKeep")
                      }
                      required={required}
                      hint={t("editor.milestone.retagNow").replace(
                        "{treatment}",
                        treatmentLabel(a.tax_treatment, t),
                      )}
                      error={errors.fields.retag}
                    />
                  );
                })}
              </div>
            </fieldset>
          )}
        </>
      )}
    </EditorDrawer>
  );
}
