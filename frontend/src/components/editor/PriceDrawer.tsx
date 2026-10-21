/** "Koers/waarde vastleggen": a per-unit price for unit-holding accounts,
 * a direct EUR value for everything else. FX happens server-side. */
import { useState } from "react";
import { type Account, useRecordManualPrice } from "../../lib/api";
import { todayLocal } from "../../lib/dates";
import { NO_ERRORS, parseApiError } from "../../lib/fieldErrors";
import { useT } from "../../lib/i18n";
import { EditorDrawer } from "./EditorDrawer";
import { DateField, DecimalField } from "./fields";

export function PriceDrawer({
  open,
  onOpenChange,
  account,
}: {
  open: boolean;
  onOpenChange: (o: boolean) => void;
  account: Account;
}) {
  const t = useT();
  const record = useRecordManualPrice();
  const [onDate, setOnDate] = useState(todayLocal);
  const [amount, setAmount] = useState("");
  const perUnit = account.units != null;
  const errors = record.isError ? parseApiError(record.error) : NO_ERRORS;

  function save() {
    record.mutate(
      {
        account_id: account.id,
        date: onDate,
        ...(perUnit ? { price: amount } : { value: amount }),
      },
      { onSuccess: () => onOpenChange(false) },
    );
  }

  return (
    <EditorDrawer
      open={open}
      onOpenChange={onOpenChange}
      title={`${t("editor.price.title")} — ${account.name}`}
      saving={record.isPending}
      error={errors.general}
      onSubmit={save}
    >
      <DecimalField
        label={
          perUnit
            ? `${t("editor.price.perUnit")} (${account.currency})`
            : t("editor.price.valueEur")
        }
        value={amount}
        onChange={setAmount}
        required
        autoFocus
        error={errors.fields.price ?? errors.fields.value}
        hint={perUnit && account.currency !== "EUR" ? t("editor.price.fxNote") : undefined}
      />
      <DateField label={t("editor.price.date")} value={onDate} onChange={setOnDate} required />
    </EditorDrawer>
  );
}
