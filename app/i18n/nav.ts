import type { MessageKey } from "./messages";

export const navKeys = [
  ["◈", "nav.dashboard"],
  ["▤", "nav.documents"],
  ["✦", "nav.chat"],
  ["□", "nav.calendar"],
  ["◫", "nav.compare"],
  ["◒", "nav.analytics"],
  ["⚙", "nav.settings"],
] as const satisfies ReadonlyArray<readonly [string, MessageKey]>;

export type NavKey = (typeof navKeys)[number][1];

export const pageMetaKeys: Record<NavKey, { title: MessageKey; subtitle: MessageKey }> = {
  "nav.dashboard": { title: "nav.dashboard", subtitle: "dashboard.subtitle" },
  "nav.documents": { title: "page.documents.title", subtitle: "page.documents.subtitle" },
  "nav.chat": { title: "page.chat.title", subtitle: "page.chat.subtitle" },
  "nav.calendar": { title: "page.calendar.title", subtitle: "page.calendar.subtitle" },
  "nav.compare": { title: "page.compare.title", subtitle: "page.compare.subtitle" },
  "nav.analytics": { title: "page.analytics.title", subtitle: "page.analytics.subtitle" },
  "nav.settings": { title: "page.settings.title", subtitle: "page.settings.subtitle" },
};
