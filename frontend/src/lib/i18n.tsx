/** Chrome translations; Dutch tax terms retain their names in both locales. */

import { setupI18n } from "@lingui/core";
import { createContext, type ReactNode, useContext, useEffect, useState } from "react";
import { messages as en } from "../locales/en.mjs";
import type { MsgKey } from "../locales/message-ids";
import { messages as nl } from "../locales/nl.mjs";
import { readStored, writeStored } from "./storage";

export type { MsgKey } from "../locales/message-ids";

export const translators = {
  en: setupI18n({ locale: "en", messages: { en } }),
  nl: setupI18n({ locale: "nl", messages: { nl } }),
};
export type Locale = keyof typeof translators;

const STORAGE_KEY = "vuurtoren-locale";

export function detectLocale(stored: string | null, navigatorLanguage: string): Locale {
  if (stored === "nl" || stored === "en") return stored;
  return navigatorLanguage.toLowerCase().startsWith("nl") ? "nl" : "en";
}

const LocaleContext = createContext<{ locale: Locale; setLocale: (l: Locale) => void } | null>(
  null,
);

export function I18nProvider({ children }: { children: ReactNode }) {
  const [locale, setLocaleState] = useState<Locale>(() =>
    detectLocale(readStored(STORAGE_KEY), navigator.language),
  );
  const setLocale = (l: Locale) => {
    writeStored(STORAGE_KEY, l);
    setLocaleState(l);
  };
  useEffect(() => {
    document.documentElement.lang = locale;
  }, [locale]);
  return <LocaleContext.Provider value={{ locale, setLocale }}>{children}</LocaleContext.Provider>;
}

function useLocaleContext() {
  const ctx = useContext(LocaleContext);
  if (!ctx) throw new Error("useT/useLocale outside <I18nProvider>");
  return ctx;
}

export function useLocale(): [Locale, (l: Locale) => void] {
  const { locale, setLocale } = useLocaleContext();
  return [locale, setLocale];
}

export function useT(): (key: MsgKey) => string {
  const { locale } = useLocaleContext();
  return (key) => translators[locale]._(key);
}
