"use client";

import { useMemo } from "react";
import { MessageKey, resolveLocale, translate } from "./messages";

export function useTranslation(language: string) {
  const locale = resolveLocale(language);
  const t = useMemo(
    () => (key: MessageKey) => translate(locale, key),
    [locale],
  );
  return { t, locale, isRtl: locale === "ar" };
}
