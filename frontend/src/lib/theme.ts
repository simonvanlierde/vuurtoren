/** Theme plumbing: system default, Settings override,
 * persisted in localStorage. The pre-paint init in index.html mirrors this —
 * keep the storage key and class in sync with it. */
import { readStored, writeStored } from "./storage";

export type ThemePref = "light" | "dark" | "system";

const STORAGE_KEY = "vuurtoren-theme";

export function resolveTheme(pref: ThemePref, systemDark: boolean): "light" | "dark" {
  if (pref === "system") return systemDark ? "dark" : "light";
  return pref;
}

export function getThemePref(): ThemePref {
  const raw = readStored(STORAGE_KEY);
  return raw === "light" || raw === "dark" ? raw : "system";
}

export function applyTheme(): void {
  const systemDark = window.matchMedia("(prefers-color-scheme: dark)").matches;
  document.documentElement.classList.toggle(
    "dark",
    resolveTheme(getThemePref(), systemDark) === "dark",
  );
}

export function setThemePref(pref: ThemePref): void {
  writeStored(STORAGE_KEY, pref === "system" ? null : pref);
  applyTheme();
}

/** React to OS theme changes while pref is "system". Call once at startup. */
export function watchSystemTheme(): void {
  window.matchMedia("(prefers-color-scheme: dark)").addEventListener("change", applyTheme);
}
