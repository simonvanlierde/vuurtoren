/** Create/edit drawer for a recurring cash flow. While an existing
 * flow's draft edits, the Flows chart re-runs as a dry-run via inline overrides —
 * a `cash_flows` patch, nothing persisted. */
import { useEffect, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  type Account,
  type CashFlow,
  type CashFlowIn,
  type CashFlowKind,
  cashFlowApi,
  type InlineOverrides,
  type Person,
} from "../../lib/api";
import { NO_ERRORS, parseApiError } from "../../lib/fieldErrors";
import { useT } from "../../lib/i18n";
import { isDecimalString } from "../../lib/money";
import { EditorDrawer } from "./EditorDrawer";
import { CheckboxField, DateField, DecimalField, SelectField, TextField } from "./fields";

const KINDS: CashFlowKind[] = ["income", "expense", "contribution"];

interface Draft {
  label: string;
  kind: CashFlowKind;
  amount_monthly: string;
  owner: string;
  target: string;
  start_date: string;
  end_date: string;
  inflation_linked: boolean;
}

function toDraft(f: CashFlow | null): Draft {
  return {
    label: f?.label ?? "",
    kind: f?.kind ?? "expense",
    amount_monthly: f?.amount_monthly ?? "",
    owner: f?.owner_person_id != null ? String(f.owner_person_id) : "",
    target: f?.target_account_id != null ? String(f.target_account_id) : "",
    start_date: f?.start_date ?? "",
    end_date: f?.end_date ?? "",
    inflation_linked: f?.inflation_linked ?? true,
  };
}

function toBody(d: Draft, householdId: number): CashFlowIn {
  return {
    household_id: householdId,
    label: d.label,
    amount_monthly: d.amount_monthly,
    kind: d.kind,
    owner_person_id: d.owner === "" ? null : Number(d.owner),
    target_account_id: d.target === "" ? null : Number(d.target),
    start_date: d.start_date === "" ? null : d.start_date,
    end_date: d.end_date === "" ? null : d.end_date,
    inflation_linked: d.inflation_linked,
  };
}

export function CashFlowDrawer({
  open,
  onOpenChange,
  cashFlow,
  householdId,
  people,
  accounts,
  onPreview,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  cashFlow: CashFlow | null;
  householdId: number;
  people: Person[];
  accounts: Account[];
  onPreview: (o: InlineOverrides | null) => void;
}) {
  const t = useT();
  const [draft, setDraft] = useState<Draft>(() => toDraft(cashFlow));
  const create = cashFlowApi.useCreate();
  const update = cashFlowApi.useUpdate();
  const remove = cashFlowApi.useDelete();
  const active = cashFlow ? update : create;
  const errors = active.isError
    ? parseApiError(active.error)
    : remove.isError
      ? parseApiError(remove.error)
      : NO_ERRORS;

  function set<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((d) => ({ ...d, [key]: value }));
  }

  // Live preview (edit only): a complete draft becomes a cash_flows patch; an
  // incomplete one clears the preview instead of 400-ing per keystroke.
  const complete = draft.label !== "" && isDecimalString(draft.amount_monthly);
  const previewJson =
    cashFlow && complete
      ? JSON.stringify((({ household_id: _hh, ...patch }) => patch)(toBody(draft, householdId)))
      : null;
  useEffect(() => {
    if (!cashFlow || previewJson == null) {
      onPreview(null);
      return;
    }
    onPreview({ cash_flows: { [cashFlow.id]: JSON.parse(previewJson) } });
  }, [cashFlow, previewJson, onPreview]);
  useEffect(() => () => onPreview(null), [onPreview]);

  function save(andAnother = false) {
    const body = toBody(draft, householdId);
    const opts = {
      onSuccess: () => (andAnother ? setDraft(toDraft(null)) : onOpenChange(false)),
    };
    if (cashFlow) update.mutate({ id: cashFlow.id, body }, opts);
    else create.mutate(body, opts);
  }

  return (
    <EditorDrawer
      open={open}
      onOpenChange={onOpenChange}
      title={cashFlow ? t("editor.flow.editTitle") : t("editor.flow.newTitle")}
      saving={active.isPending}
      error={errors.general}
      onSubmit={() => save()}
      onDelete={
        cashFlow
          ? () => remove.mutate(cashFlow.id, { onSuccess: () => onOpenChange(false) })
          : undefined
      }
      submitExtra={
        cashFlow ? undefined : (
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
        label={t("editor.flow.label")}
        value={draft.label}
        onChange={(v) => set("label", v)}
        required
        autoFocus
        error={errors.fields.label}
      />
      <SelectField
        label={t("editor.flow.kind")}
        value={draft.kind}
        onChange={(v) => set("kind", v as CashFlowKind)}
        options={KINDS.map((k) => ({ value: k, label: t(`flows.kind.${k}`) }))}
        error={errors.fields.kind}
      />
      <DecimalField
        label={t("editor.flow.amount")}
        value={draft.amount_monthly}
        onChange={(v) => set("amount_monthly", v)}
        required
        error={errors.fields.amount_monthly}
      />
      <SelectField
        label={t("editor.flow.owner")}
        value={draft.owner}
        onChange={(v) => set("owner", v)}
        options={people.map((p) => ({ value: String(p.id), label: p.name }))}
        emptyLabel={t("editor.account.household")}
        error={errors.fields.owner_person_id}
      />
      <SelectField
        label={t("editor.flow.target")}
        value={draft.target}
        onChange={(v) => set("target", v)}
        options={accounts.map((a) => ({ value: String(a.id), label: a.name }))}
        emptyLabel="—"
        hint={t("editor.flow.targetHint")}
        error={errors.fields.target_account_id}
      />
      <DateField
        label={t("editor.flow.start")}
        value={draft.start_date}
        onChange={(v) => set("start_date", v)}
        error={errors.fields.start_date}
      />
      <DateField
        label={t("editor.flow.end")}
        value={draft.end_date}
        onChange={(v) => set("end_date", v)}
        error={errors.fields.end_date}
      />
      <CheckboxField
        label={t("editor.flow.indexed")}
        checked={draft.inflation_linked}
        onChange={(v) => set("inflation_linked", v)}
        hint={t("editor.flow.indexedHint")}
      />
    </EditorDrawer>
  );
}
