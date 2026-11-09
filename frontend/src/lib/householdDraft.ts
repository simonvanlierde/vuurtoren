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
