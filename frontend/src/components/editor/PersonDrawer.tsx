/** Create/edit drawer for a household member. Same shape as CashFlowDrawer,
 * minus the live preview — a person edit has no dry-run projection. */
import { useState } from "react";
import { Button } from "@/components/ui/button";
import {
  FILING_STATUSES,
  type FilingStatus,
  type Person,
  type PersonIn,
  personApi,
} from "../../lib/api";
import { NO_ERRORS, parseApiError } from "../../lib/fieldErrors";
import { useT } from "../../lib/i18n";
import { EditorDrawer } from "./EditorDrawer";
import { CheckboxField, DateField, SelectField, TextField } from "./fields";

interface Draft {
  name: string;
  birth_date: string;
  tax_residence: string;
  pension_age_override: string;
  us_person: boolean;
  us_filing_status: FilingStatus;
}

function toDraft(p: Person | null): Draft {
  return {
    name: p?.name ?? "",
    birth_date: p?.birth_date ?? "",
    tax_residence: p?.tax_residence ?? "NL",
    pension_age_override: p?.pension_age_override ?? "",
    us_person: p?.us_person ?? false,
    // The overlay's own fallback is single, and the reason is written there. Asking
    // explicitly is what this field is for, so the draft starts where the fallback does
    // rather than empty — MFS is a US citizen's usual status when the spouse is not one,
    // but guessing at a marriage from a person row would be worse than showing a default.
    us_filing_status: p?.us_filing_status ?? "single",
  };
}

function toBody(d: Draft, householdId: number): PersonIn {
  return {
    household_id: householdId,
    name: d.name,
    birth_date: d.birth_date,
    tax_residence: d.tax_residence,
    pension_age_override:
      d.pension_age_override.trim() === "" ? null : d.pension_age_override.trim(),
    us_person: d.us_person,
    // Cleared when the box is unticked: a stored status on a non-US person is a fact
    // about nothing, and it would come back if the box were ever reticked by accident.
    us_filing_status: d.us_person ? d.us_filing_status : null,
  };
}

export function PersonDrawer({
  open,
  onOpenChange,
  person,
  householdId,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  person: Person | null;
  householdId: number;
}) {
  const t = useT();
  const [draft, setDraft] = useState<Draft>(() => toDraft(person));
  const create = personApi.useCreate();
  const update = personApi.useUpdate();
  const remove = personApi.useDelete();
  const active = person ? update : create;
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
    if (person) update.mutate({ id: person.id, body }, opts);
    else create.mutate(body, opts);
  }

  return (
    <EditorDrawer
      open={open}
      onOpenChange={onOpenChange}
      title={person ? t("editor.person.editTitle") : t("editor.person.newTitle")}
      saving={active.isPending}
      error={errors.general}
      onSubmit={() => save()}
      onDelete={
        person
          ? () => remove.mutate(person.id, { onSuccess: () => onOpenChange(false) })
          : undefined
      }
      submitExtra={
        person ? undefined : (
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
        label={t("editor.person.name")}
        value={draft.name}
        onChange={(v) => set("name", v)}
        required
        autoFocus
        error={errors.fields.name}
      />
      <DateField
        label={t("editor.person.birth")}
        value={draft.birth_date}
        onChange={(v) => set("birth_date", v)}
        required
        error={errors.fields.birth_date}
      />
      <TextField
        label={t("editor.person.residence")}
        value={draft.tax_residence}
        onChange={(v) => set("tax_residence", v)}
        error={errors.fields.tax_residence}
      />
      <TextField
        label={t("editor.person.pensionOverride")}
        value={draft.pension_age_override}
        onChange={(v) => set("pension_age_override", v)}
        placeholder="67y3m"
        hint={t("editor.person.pensionHint")}
        error={errors.fields.pension_age_override}
      />
      <CheckboxField
        label={t("editor.person.usPerson")}
        checked={draft.us_person}
        onChange={(v) => set("us_person", v)}
        hint={t("editor.person.usPersonHint")}
      />
      {draft.us_person && (
        <>
          <SelectField
            label={t("editor.person.filingStatus")}
            value={draft.us_filing_status}
            onChange={(v) => set("us_filing_status", v as FilingStatus)}
            options={FILING_STATUSES.map((s) => ({
              value: s,
              label: t(`editor.person.filing.${s}`),
            }))}
            hint={t("editor.person.filingHint")}
            error={errors.fields.us_filing_status}
          />
          {/* The caveat phase 4 owed the user: the credit for Box 3 rests on relief
              Treasury can withdraw, not on settled law. It belongs where the fact is
              declared, because that is the moment the projection starts depending on it. */}
          <p className="text-xs text-ink-navy/70 dark:text-paper/60">
            {t("editor.person.usCaveat")}
          </p>
        </>
      )}
    </EditorDrawer>
  );
}
