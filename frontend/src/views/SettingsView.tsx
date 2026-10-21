import { type ChangeEvent, useEffect, useId, useMemo, useRef, useState } from "react";
import { Button } from "@/components/ui/button";
import {
  CheckboxField,
  NativeSelect,
  NumberField,
  SelectField,
  TextField,
} from "../components/editor/fields";
import { PersonDrawer } from "../components/editor/PersonDrawer";
import { DataTable } from "../components/ui/DataTable";
import {
  ApiError,
  fetchExportDoc,
  type Household,
  householdApi,
  type Person,
  useDeleteHouseholdAll,
  useHouseholds,
  useImportHousehold,
  usePeople,
  usePricePoints,
  useTaxCountries,
} from "../lib/api";
import { latestUsdRate, useDisplayCurrency } from "../lib/displayCurrency";
import { NO_ERRORS, parseApiError } from "../lib/fieldErrors";
import { useLocale, useT } from "../lib/i18n";
import { getThemePref, setThemePref, type ThemePref } from "../lib/theme";
import { useRawHash } from "../lib/useHash";

function HouseholdSection({ household }: { household: Household }) {
  const t = useT();
  const taxCountries = useTaxCountries();
  const update = householdApi.useUpdate();
  const [draft, setDraft] = useState({
    name: household.name,
    tax_country: household.tax_country,
    fiscal_partners: household.fiscal_partners,
    life_expectancy_age: String(household.life_expectancy_age),
  });
  const errors = update.isError ? parseApiError(update.error) : NO_ERRORS;

  function edit(patch: Partial<typeof draft>) {
    if (update.isSuccess) update.reset();
    setDraft((d) => ({ ...d, ...patch }));
  }

  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        update.mutate({
          id: household.id,
          body: {
            name: draft.name,
            base_currency: household.base_currency,
            tax_country: draft.tax_country,
            fiscal_partners: draft.fiscal_partners,
            life_expectancy_age: Number(draft.life_expectancy_age),
          },
        });
      }}
      className="space-y-4"
    >
      <h2 className="font-display text-lg">{t("settings.household.title")}</h2>
      <TextField
        label={t("settings.household.name")}
        value={draft.name}
        onChange={(v) => edit({ name: v })}
        required
        error={errors.fields.name}
      />
      {/* The registered regimes, not free text, so a typo cannot reach the projection.
          The list comes from the server, so it cannot go stale. */}
      <SelectField
        label={t("settings.household.taxCountry")}
        value={draft.tax_country}
        onChange={(v) => edit({ tax_country: v })}
        options={[...(taxCountries.data ?? [draft.tax_country])]
          // NL first, not alphabetical: a Dutch-first product's default country should
          // not sort itself behind Austria.
          .sort((a, b) => (a === "NL" ? -1 : b === "NL" ? 1 : a.localeCompare(b)))
          .map((c) => ({
            value: c,
            label: c,
          }))}
        hint={t("settings.household.taxCountryHint")}
        error={errors.fields.tax_country}
      />
      <CheckboxField
        label={t("settings.household.fiscalPartners")}
        checked={draft.fiscal_partners}
        onChange={(v) => edit({ fiscal_partners: v })}
      />
      <NumberField
        label={t("settings.household.lifeExpectancy")}
        value={draft.life_expectancy_age}
        onChange={(v) => edit({ life_expectancy_age: v })}
        error={errors.fields.life_expectancy_age}
      />
      <p className="text-xs text-ink-navy/70 dark:text-paper/60">
        {t("settings.household.baseCurrency")}: EUR
      </p>
      {errors.general && (
        <p role="alert" className="text-sm text-brick">
          {errors.general}
        </p>
      )}
      <Button type="submit" disabled={update.isPending}>
        {update.isSuccess && !update.isPending ? t("settings.household.saved") : t("editor.save")}
      </Button>
    </form>
  );
}

function CreateHouseholdSection() {
  const t = useT();
  const create = householdApi.useCreate();
  const [name, setName] = useState("");
  const errors = create.isError ? parseApiError(create.error) : NO_ERRORS;
  return (
    <form
      onSubmit={(e) => {
        e.preventDefault();
        create.mutate({
          name,
          base_currency: "EUR",
          tax_country: "NL",
          fiscal_partners: false,
          life_expectancy_age: 95,
        });
      }}
      className="space-y-4"
    >
      <h2 className="font-display text-lg">{t("settings.household.title")}</h2>
      <p className="max-w-prose text-sm text-ink-navy/70 dark:text-paper/70">
        {t("empty.createHousehold")}
      </p>
      <TextField
        label={t("settings.household.name")}
        value={name}
        onChange={setName}
        required
        error={errors.fields.name}
      />
      {errors.general && (
        <p role="alert" className="text-sm text-brick">
          {errors.general}
        </p>
      )}
      <Button type="submit" disabled={create.isPending}>
        {t("empty.createHousehold.cta")}
      </Button>
    </form>
  );
}

function PeopleSection({ householdId, people }: { householdId: number; people: Person[] }) {
  const t = useT();
  const [editing, setEditing] = useState<{ person: Person | null } | null>(null);

  return (
    <section className="space-y-4">
      <div className="flex items-baseline justify-between">
        <h2 className="font-display text-lg">{t("settings.people.title")}</h2>
        <Button type="button" onClick={() => setEditing({ person: null })} variant="emphasis">
          {t("settings.people.add")}
        </Button>
      </div>
      <DataTable
        caption={t("settings.people.title")}
        rows={people}
        rowKey={(person) => String(person.id)}
        columns={[
          { header: t("editor.person.name"), title: true, cell: (person) => person.name },
          { header: t("settings.people.birth"), cell: (person) => person.birth_date },
          { header: t("settings.people.residence"), cell: (person) => person.tax_residence },
          {
            header: t("settings.people.pension"),
            cell: (person) => person.pension_age_override ?? "—",
          },
          {
            header: t("today.actions"),
            headerHidden: true,
            full: true,
            cell: (person) => (
              <div className="-my-2 flex sm:justify-end">
                <Button
                  type="button"
                  onClick={() => setEditing({ person })}
                  aria-label={`${t("today.edit")}: ${person.name}`}
                  variant="link"
                >
                  {t("today.edit")}
                </Button>
              </div>
            ),
          },
        ]}
      />

      {editing && (
        <PersonDrawer
          key={editing.person?.id ?? "new"}
          open
          onOpenChange={(o) => {
            if (!o) setEditing(null);
          }}
          person={editing.person}
          householdId={householdId}
        />
      )}
    </section>
  );
}

/** "Start with an empty household": deletes the stored household and everything in it,
 * behind an inline confirmation because it cannot be undone. The banner's "Settings is
 * where you replace them" links here (`#settings/start-empty`), and the import conflict
 * message points here. Afterwards the app lands on Today's first-run flow. */
function StartEmptySection({ household }: { household: Household }) {
  const t = useT();
  const hash = useRawHash();
  const remove = useDeleteHouseholdAll();
  const [confirming, setConfirming] = useState(false);
  const startRef = useRef<HTMLButtonElement>(null);
  const cancelRef = useRef<HTMLButtonElement>(null);
  const confirmId = useId();

  useEffect(() => {
    if (hash === "#settings/start-empty") {
      startRef.current?.scrollIntoView({ block: "center" });
      startRef.current?.focus();
    }
  }, [hash]);
  // The safe choice takes focus when the destructive one appears.
  useEffect(() => {
    if (confirming) cancelRef.current?.focus();
  }, [confirming]);

  return (
    <div className="space-y-2 border-t border-ink-navy/10 pt-3 dark:border-paper/10">
      {confirming ? (
        <div className="space-y-2">
          <p id={confirmId} className="max-w-prose text-sm">
            {t("settings.backup.startEmpty.confirm").replace("{name}", household.name)}
          </p>
          <div className="flex flex-wrap gap-3">
            <Button
              type="button"
              variant="destructive"
              aria-describedby={confirmId}
              disabled={remove.isPending}
              // mutateAsync, not mutate's onSuccess: the refetch it triggers unmounts this
              // section (no household left), and an unmounted observer's callbacks never run.
              onClick={
                () =>
                  remove
                    .mutateAsync(household.id)
                    .then(() => {
                      window.location.hash = "#today";
                    })
                    .catch(() => {}) // shown from remove.error below
              }
            >
              {t("settings.backup.startEmpty.yes")}
            </Button>
            <Button
              ref={cancelRef}
              aria-describedby={confirmId}
              type="button"
              variant="outline"
              onClick={() => {
                setConfirming(false);
                startRef.current?.focus();
              }}
            >
              {t("editor.cancel")}
            </Button>
          </div>
        </div>
      ) : (
        <Button
          ref={startRef}
          id="start-empty"
          type="button"
          variant="outline"
          onClick={() => setConfirming(true)}
        >
          {t("settings.backup.startEmpty")}
        </Button>
      )}
      <p className="max-w-prose text-xs text-ink-navy/70 dark:text-paper/60">
        {t("settings.backup.startEmpty.hint")}
      </p>
      {remove.isError && (
        <p role="alert" className="text-sm text-brick">
          {parseApiError(remove.error).general}
        </p>
      )}
    </div>
  );
}

/** Backup & restore: export the whole household as one JSON document, and
 * import one back. Import lands only into an empty database — the server 409s on any
 * id collision — so the failure is surfaced rather than a merge attempted. This is
 * also the browser (Pyodide) build's persistence: export to save, import to restore. */
function BackupSection({ household }: { household: Household | undefined }) {
  const t = useT();
  const importHousehold = useImportHousehold();
  const [imported, setImported] = useState<number | null>(null);
  const [parseError, setParseError] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  async function onExport() {
    setExporting(true);
    try {
      const doc = await fetchExportDoc();
      const url = URL.createObjectURL(
        new Blob([JSON.stringify(doc)], { type: "application/json" }),
      );
      const a = document.createElement("a");
      a.href = url;
      a.download = "vuurtoren-export.json";
      a.click();
      URL.revokeObjectURL(url);
    } finally {
      setExporting(false);
    }
  }

  function onFile(e: ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // let the same file be re-picked after an error
    if (!file) return;
    setImported(null);
    setParseError(null);
    importHousehold.reset();
    file
      .text()
      .then((text) => {
        const doc = JSON.parse(text);
        importHousehold.mutate(doc, { onSuccess: (r) => setImported(r.household_id) });
      })
      .catch(() => setParseError(t("settings.backup.notJson")));
  }

  const serverError =
    importHousehold.error instanceof ApiError && importHousehold.error.status === 409
      ? t("settings.backup.importConflict")
      : importHousehold.error instanceof ApiError
        ? String(importHousehold.error.detail ?? importHousehold.error.message)
        : importHousehold.error
          ? String(importHousehold.error)
          : null;

  return (
    <section className="space-y-3">
      <h2 className="font-display text-lg">{t("settings.backup.title")}</h2>
      <p className="max-w-prose text-sm text-ink-navy/70 dark:text-paper/70">
        {t("settings.backup.intro")}
      </p>
      <div className="flex flex-wrap items-center gap-3">
        <Button type="button" onClick={onExport} disabled={exporting} variant="emphasis">
          {t("settings.backup.export")}
        </Button>
        {/* The input is sr-only, so the label draws the focus the input receives. */}
        <label className="inline-flex h-8 min-h-11 cursor-pointer items-center rounded-lg border border-ink-navy px-2.5 text-sm font-medium sm:min-h-0 has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-ring dark:border-paper">
          {importHousehold.isPending ? t("settings.backup.importing") : t("settings.backup.import")}
          <input
            type="file"
            accept="application/json,.json"
            onChange={onFile}
            className="sr-only"
          />
        </label>
      </div>
      {imported !== null && (
        <p className="text-sm text-ink-navy/70 dark:text-paper/70">
          {t("settings.backup.imported")}
        </p>
      )}
      {(parseError ?? serverError) && (
        <p role="alert" className="text-sm text-brick">
          {parseError ?? serverError}
        </p>
      )}
      {household && <StartEmptySection household={household} />}
    </section>
  );
}

export function SettingsView() {
  const t = useT();
  const [locale, setLocale] = useLocale();
  const [theme, setTheme] = useState<ThemePref>(getThemePref);
  const { pref, setPref } = useDisplayCurrency();
  const pricePoints = usePricePoints();
  const usdRate = useMemo(() => latestUsdRate(pricePoints.data ?? []), [pricePoints.data]);
  const households = useHouseholds();
  const people = usePeople();
  const household = households.data?.[0];

  return (
    <div className="max-w-2xl space-y-8 p-4 sm:p-8">
      <h1 className="font-display text-2xl">{t("settings.title")}</h1>

      <div className="space-y-2">
        <label htmlFor="settings-language" className="text-sm font-medium">
          {t("settings.language")}
        </label>
        <NativeSelect
          id="settings-language"
          value={locale}
          onChange={(e) => setLocale(e.target.value as "nl" | "en")}
        >
          <option value="nl">Nederlands</option>
          <option value="en">English</option>
        </NativeSelect>
      </div>

      <div className="space-y-2">
        <label htmlFor="settings-theme" className="text-sm font-medium">
          {t("settings.theme")}
        </label>
        <NativeSelect
          id="settings-theme"
          value={theme}
          onChange={(e) => {
            setThemePref(e.target.value as ThemePref);
            setTheme(e.target.value as ThemePref);
          }}
        >
          <option value="system">{t("settings.theme.system")}</option>
          <option value="light">{t("settings.theme.light")}</option>
          <option value="dark">{t("settings.theme.dark")}</option>
        </NativeSelect>
      </div>

      <div className="space-y-2">
        <label htmlFor="settings-currency" className="text-sm font-medium">
          {t("settings.currency")}
        </label>
        <NativeSelect
          id="settings-currency"
          value={pref}
          onChange={(e) => setPref(e.target.value as typeof pref)}
        >
          <option value="EUR">{t("settings.currency.eur")}</option>
          <option value="USD" disabled={usdRate === null}>
            {t("settings.currency.usd")}
          </option>
          <option value="quote">{t("settings.currency.quote")}</option>
        </NativeSelect>
        {usdRate && (
          <p className="text-xs text-ink-navy/70 dark:text-paper/60">
            1 EUR = {usdRate.usdPerEur.toFixed(4)} USD{" "}
            <span className="tabular-nums">(ECB, {usdRate.date})</span>
          </p>
        )}
        {!usdRate && pref === "USD" ? (
          // A pref persisted as USD (from an earlier session) with no rate now would
          // otherwise render EUR everywhere while this select still reads "USD" — say so.
          <p role="alert" className="text-xs text-brick">
            {t("settings.currency.usdFallback")}
          </p>
        ) : (
          !usdRate && (
            <p className="text-xs text-ink-navy/70 dark:text-paper/60">
              {t("settings.currency.noRate")}
            </p>
          )
        )}
      </div>

      {households.data && households.data.length === 0 && <CreateHouseholdSection />}
      {household && (
        <>
          {/* NOTE: content-keyed so the draft resyncs whenever the server object
              changes (e.g. after a save's refetch). In-progress edits are only
              discarded when the stored household actually changed — acceptable
              for a single-user app. */}
          <HouseholdSection key={JSON.stringify(household)} household={household} />
          <PeopleSection householdId={household.id} people={people.data ?? []} />
        </>
      )}

      <BackupSection household={household} />
    </div>
  );
}
