import type { Household } from "./api";

/** The Settings form's editable household fields. The age is a string so a blank field
 * can exist while the user types. */
export interface HouseholdDraft {
  name: string;
  tax_country: string;
  fiscal_partners: boolean;
  life_expectancy_age: string;
}

export function draftFrom(h: Household): HouseholdDraft {
  return {
    name: h.name,
    tax_country: h.tax_country,
    fiscal_partners: h.fiscal_partners,
    life_expectancy_age: String(h.life_expectancy_age),
  };
}

/** The form shows the server copy with the user's edits laid over it, so a field they
 * never touched follows a refetch instead of being sent back as a stale value. */
export function withEdits(h: Household, edits: Partial<HouseholdDraft>): HouseholdDraft {
  return { ...draftFrom(h), ...edits };
}

/** Forget the edits a save has now stored. An edit typed while the save was pending
 * differs from what was submitted, so it stays. */
export function dropSaved(
  edits: Partial<HouseholdDraft>,
  submitted: HouseholdDraft,
): Partial<HouseholdDraft> {
  return Object.fromEntries(
    Object.entries(edits).filter(([k, v]) => v !== submitted[k as keyof HouseholdDraft]),
  );
}

export function isDirty(draft: HouseholdDraft, h: Household): boolean {
  return (
    draft.name !== h.name ||
    draft.tax_country !== h.tax_country ||
    draft.fiscal_partners !== h.fiscal_partners ||
    Number(draft.life_expectancy_age) !== h.life_expectancy_age
  );
}

/** A blank age would send 0, so Save stays off until it holds a whole number. */
export function isSavable(draft: HouseholdDraft, h: Household): boolean {
  return isDirty(draft, h) && /^\d+$/.test(draft.life_expectancy_age.trim());
}

/** Which status line explains the draft: a blocked Save names its cause. */
export function draftStatus(draft: HouseholdDraft, h: Household): "invalidAge" | "unsaved" | null {
  if (!isDirty(draft, h)) return null;
  return isSavable(draft, h) ? "unsaved" : "invalidAge";
}
