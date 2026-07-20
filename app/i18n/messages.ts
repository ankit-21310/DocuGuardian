export type MessageKey =
  | "nav.dashboard" | "nav.documents" | "nav.chat" | "nav.calendar" | "nav.compare" | "nav.analytics" | "nav.settings"
  | "workspace" | "signOut" | "uploadDocument" | "loadingWorkspace"
  | "dashboard.greetingMorning" | "dashboard.greetingAfternoon" | "dashboard.greetingEvening" | "dashboard.subtitle"
  | "stat.documents" | "stat.highRisk" | "stat.deadlines" | "stat.protection" | "stat.fraudFlags"
  | "report.title" | "report.empty" | "report.emptyVoiceHint" | "report.download" | "report.translate" | "report.translating" | "report.voice" | "report.voiceDesc" | "report.voiceLoading" | "report.voicePlay" | "report.voiceLanguage"
  | "report.exportTitle" | "report.exportDesc" | "report.generatePdf" | "report.generatingPdf" | "report.pdfReady" | "report.downloadJson" | "report.downloadLanguage"
  | "report.voiceGenerate" | "report.voiceRegenerate" | "report.voiceGenerating"
  | "report.riskAnalysis" | "report.hiddenPenalties" | "report.clauses" | "report.keyDetails" | "report.obligations"
  | "report.fraudIndicators" | "report.fraudDisclaimer" | "report.deadlines" | "report.actionPlan" | "report.recommendations"
  | "report.evidence" | "report.noRisks" | "report.noPenalties" | "report.noClauses" | "report.noEntities"
  | "report.noObligations" | "report.noFraud" | "report.noDeadlines" | "report.noActions" | "report.noRecommendations"
  | "report.noEvidence" | "report.party"
  | "compare.title" | "compare.needTwo" | "compare.button" | "compare.similarity" | "compare.riskDelta"
  | "compare.riskLevelChanged" | "compare.deadlineChanges" | "compare.addedRisks" | "compare.removedRisks"
  | "compare.addedDeadlines" | "compare.removedDeadlines" | "compare.addedClauses" | "compare.removedClauses"
  | "compare.modifiedClauses" | "compare.failed"
  | "settings.account" | "settings.language" | "settings.languageHint" | "settings.features" | "settings.notifications"
  | "settings.audit" | "settings.calendar" | "settings.connectGoogle" | "settings.connectOutlook" | "settings.disconnect"
  | "settings.syncNow" | "settings.autoSync" | "settings.calendarConnected" | "settings.calendarFailed"
  | "settings.noNotifications" | "settings.noAudit";

export type LocaleCode = "en" | "es" | "hi" | "fr" | "de" | "ar" | "pt" | "zh" | "ja" | "mr" | "ta";

export const LANGUAGE_TO_LOCALE: Record<string, LocaleCode> = {
  English: "en",
  Spanish: "es",
  Hindi: "hi",
  French: "fr",
  German: "de",
  Arabic: "ar",
  Portuguese: "pt",
  "Chinese (Simplified)": "zh",
  Japanese: "ja",
  Marathi: "mr",
  Tamil: "ta",
};

const en: Record<MessageKey, string> = {
  "nav.dashboard": "Dashboard",
  "nav.documents": "Documents",
  "nav.chat": "AI Chat",
  "nav.calendar": "Calendar",
  "nav.compare": "Compare",
  "nav.analytics": "Analytics",
  "nav.settings": "Settings",
  workspace: "Workspace",
  signOut: "Sign out",
  uploadDocument: "Upload document",
  loadingWorkspace: "Loading workspace…",
  "dashboard.greetingMorning": "Good morning",
  "dashboard.greetingAfternoon": "Good afternoon",
  "dashboard.greetingEvening": "Good evening",
  "dashboard.subtitle": "Here's what's happening with your documents.",
  "stat.documents": "Documents uploaded",
  "stat.highRisk": "High risk documents",
  "stat.deadlines": "Upcoming deadlines",
  "stat.protection": "Protection score",
  "stat.fraudFlags": "Fraud-flagged documents",
  "report.title": "Intelligence report",
  "report.empty": "Select an analyzed document to review its summary, risks, clauses, obligations, deadlines, action plan, and source evidence.",
  "report.emptyVoiceHint": "Click Report → on a completed document. A Voice summary player will appear at the top of the report.",
  "report.download": "Download report",
  "report.exportTitle": "Export report",
  "report.exportDesc": "Select a language, then generate your report as a PDF.",
  "report.generatePdf": "Generate PDF report",
  "report.generatingPdf": "Generating report…",
  "report.pdfReady": "PDF report ready",
  "report.downloadJson": "Download JSON",
  "report.downloadLanguage": "Report language",
  "report.translate": "Translate to",
  "report.translating": "Translating…",
  "report.voice": "Voice summary",
  "report.voiceDesc": "Select a language first, then generate an audio summary.",
  "report.voiceLoading": "Generating audio…",
  "report.voicePlay": "Play voice summary",
  "report.voiceGenerate": "Generate voice summary",
  "report.voiceRegenerate": "Regenerate",
  "report.voiceGenerating": "Generating audio…",
  "report.voiceLanguage": "Voice language",
  "report.riskAnalysis": "Risk analysis",
  "report.hiddenPenalties": "Hidden penalties",
  "report.clauses": "Clauses",
  "report.keyDetails": "Key details",
  "report.obligations": "Obligations",
  "report.fraudIndicators": "Fraud indicators",
  "report.fraudDisclaimer": "Assistive signals only—not proof of fraud or legal findings.",
  "report.deadlines": "Deadlines",
  "report.actionPlan": "Action plan",
  "report.recommendations": "Recommendations",
  "report.evidence": "Evidence",
  "report.noRisks": "No risks were extracted.",
  "report.noPenalties": "No hidden penalties detected.",
  "report.noClauses": "No clauses were extracted.",
  "report.noEntities": "No key details were extracted.",
  "report.noObligations": "No obligations were extracted.",
  "report.noFraud": "No fraud indicators were detected.",
  "report.noDeadlines": "No deadlines were extracted.",
  "report.noActions": "No action plan items were extracted.",
  "report.noRecommendations": "No recommendations were extracted.",
  "report.noEvidence": "No evidence spans were returned.",
  "report.party": "Party",
  "compare.title": "Select two analyzed documents",
  "compare.needTwo": "Upload and complete analysis for another document before comparing.",
  "compare.button": "Compare documents",
  "compare.similarity": "report similarity",
  "compare.riskDelta": "Risk score change",
  "compare.riskLevelChanged": "Risk level changed between documents",
  "compare.deadlineChanges": "Deadline date changes",
  "compare.addedRisks": "Added risks",
  "compare.removedRisks": "Removed risks",
  "compare.addedDeadlines": "Added deadlines",
  "compare.removedDeadlines": "Removed deadlines",
  "compare.addedClauses": "Added clauses",
  "compare.removedClauses": "Removed clauses",
  "compare.modifiedClauses": "Modified clauses",
  "compare.failed": "Unable to compare these documents.",
  "settings.account": "Account",
  "settings.language": "Preferred language",
  "settings.languageHint": "Used for UI chrome, AI Chat responses, and document report translations.",
  "settings.features": "Feature flags",
  "settings.notifications": "Notifications",
  "settings.audit": "Audit log",
  "settings.calendar": "Calendar integrations",
  "settings.connectGoogle": "Connect Google Calendar",
  "settings.connectOutlook": "Connect Outlook Calendar",
  "settings.disconnect": "Disconnect",
  "settings.syncNow": "Sync all deadlines",
  "settings.autoSync": "Auto-sync new deadlines",
  "settings.calendarConnected": "Calendar connected.",
  "settings.calendarFailed": "Calendar connection failed.",
  "settings.noNotifications": "No notifications yet.",
  "settings.noAudit": "Audit events appear for owners and admins.",
};

const es: Partial<Record<MessageKey, string>> = {
  "nav.dashboard": "Panel",
  "nav.documents": "Documentos",
  "nav.chat": "Chat IA",
  "nav.calendar": "Calendario",
  "nav.compare": "Comparar",
  "nav.analytics": "Analítica",
  "nav.settings": "Ajustes",
  signOut: "Cerrar sesión",
  uploadDocument: "Subir documento",
  "report.obligations": "Obligaciones",
  "report.keyDetails": "Detalles clave",
  "report.fraudIndicators": "Indicadores de fraude",
  "compare.deadlineChanges": "Cambios de fechas",
  "settings.calendar": "Integraciones de calendario",
};

const ar: Partial<Record<MessageKey, string>> = {
  "nav.dashboard": "لوحة التحكم",
  "nav.documents": "المستندات",
  "nav.chat": "محادثة الذكاء الاصطناعي",
  "nav.calendar": "التقويم",
  "nav.compare": "مقارنة",
  "nav.analytics": "التحليلات",
  "nav.settings": "الإعدادات",
  signOut: "تسجيل الخروج",
  uploadDocument: "رفع مستند",
  "report.obligations": "الالتزامات",
  "report.keyDetails": "التفاصيل الرئيسية",
  "report.fraudIndicators": "مؤشرات الاحتيال",
};

const hi: Partial<Record<MessageKey, string>> = {
  "nav.dashboard": "डैशबोर्ड",
  "nav.documents": "दस्तावेज़",
  "nav.chat": "AI चैट",
  "report.obligations": "दायित्व",
  "report.keyDetails": "मुख्य विवरण",
};

export const MESSAGES: Record<LocaleCode, Record<MessageKey, string>> = {
  en,
  es: { ...en, ...es },
  hi: { ...en, ...hi },
  fr: { ...en },
  de: { ...en },
  ar: { ...en, ...ar },
  pt: { ...en },
  zh: { ...en },
  ja: { ...en },
  mr: { ...en },
  ta: { ...en },
};

export function resolveLocale(language: string): LocaleCode {
  return LANGUAGE_TO_LOCALE[language] || "en";
}

export function translate(locale: LocaleCode, key: MessageKey): string {
  return MESSAGES[locale]?.[key] || MESSAGES.en[key] || key;
}
