"use client";

import { createContext, useContext, useEffect, useMemo, useState } from "react";
import {
  DEFAULT_LANGUAGE,
  getMessage,
  getStatusLabel,
  type AppLanguage,
  PAYFI_LANG_STORAGE_KEY,
} from "./i18n";

type I18nContextValue = {
  lang: AppLanguage;
  setLang: (lang: AppLanguage) => void;
  t: (key: string) => string;
  statusLabel: (status: string | null | undefined) => string;
};

const I18nContext = createContext<I18nContextValue | null>(null);

type I18nProviderProps = {
  children: React.ReactNode;
};

function isLanguage(value: string | null): value is AppLanguage {
  return value === "zh" || value === "en";
}

export function I18nProvider({ children }: I18nProviderProps) {
  const [lang, setLangState] = useState<AppLanguage>(DEFAULT_LANGUAGE);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(PAYFI_LANG_STORAGE_KEY);
      if (isLanguage(stored)) {
        setLangState(stored);
      }
    } catch {
      // Ignore localStorage read failures.
    }
  }, []);

  const value = useMemo<I18nContextValue>(() => {
    return {
      lang,
      setLang: (nextLang) => {
        setLangState(nextLang);
        try {
          window.localStorage.setItem(PAYFI_LANG_STORAGE_KEY, nextLang);
        } catch {
          // Ignore localStorage write failures.
        }
      },
      t: (key: string) => getMessage(lang, key),
      statusLabel: (status) => getStatusLabel(lang, status),
    };
  }, [lang]);

  return <I18nContext.Provider value={value}>{children}</I18nContext.Provider>;
}

export function useI18n(): I18nContextValue {
  const context = useContext(I18nContext);
  if (!context) {
    throw new Error("useI18n must be used within I18nProvider");
  }
  return context;
}
