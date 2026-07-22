"use client";

import { ChangeEvent, DragEvent, FormEvent, Fragment, useEffect, useMemo, useRef, useState } from "react";
import { useTranslation } from "./i18n/useTranslation";
import { navKeys, pageMetaKeys, type NavKey } from "./i18n/nav";
import type { MessageKey } from "./i18n/messages";

type User = { id: string; email: string; name: string; role: string; organization_id: string };
type DocumentItem = { id: string; name: string; content_type: string; size: number; status: string; stage?: string; progress: number; risk_level?: "high" | "medium" | "low"; risk_score?: number; classification?: string; created_at: string; updated_at: string; report?: Report | null };
type Stage = { stage: string; status: string; progress: number; error?: string | null };
type Deadline = { id: string; document_id: string; title: string; due_date: string; priority: string; source: string; timezone?: string; document_name?: string };
type Analytics = { documents_uploaded: number; high_risk_documents: number; medium_risk_documents: number; low_risk_documents: number; average_risk_score: number; protection_score: number; upcoming_deadlines: number; fraud_flagged_documents?: number; categories?: Array<{ category: string; count: number }>; monthly_uploads?: Array<{ month: string; count: number }> };
type Risk = { title: string; severity: string; explanation: string; recommendation: string; source: string; page?: number | null; text_span?: string | null; confidence?: number; is_penalty?: boolean };
type Clause = { title: string; body: string; severity: string; category: string; page?: number | null; text_span?: string | null; confidence?: number };
type ActionItem = { id?: string; title: string; detail: string; priority: string; due_date?: string | null; status?: string };
type Entity = { label: string; value: string; confidence?: number; page?: number | null; text_span?: string | null };
type Obligation = { title: string; party: string; description: string; severity: string; due_date?: string | null; page?: number | null; text_span?: string | null; confidence?: number };
type FraudIndicator = { title: string; indicator_type: string; severity: string; explanation: string; page?: number | null; text_span?: string | null; confidence?: number };
type Report = { summary: string; classification: string; risk_score: number; risk_level: string; confidence: number; risks: Risk[]; entities?: Entity[]; clauses?: Clause[]; obligations?: Obligation[]; fraud_indicators?: FraudIndicator[]; hidden_penalties?: Risk[]; deadlines: Array<{ title: string; date: string; priority: string; source: string; page?: number | null }>; recommendations: string[]; action_plan?: ActionItem[]; evidence?: Array<{ page?: number | null; text_span: string; label: string; confidence: number }>; model_version?: string };
type ChatMessage = {
  role: "ai" | "user";
  text: string;
  citations?: Array<{ label: string; page?: number; confidence?: number }>;
  suggestedPrompts?: string[];
};
type ChatSessionItem = {
  id: string;
  document_id: string;
  document_name: string;
  title: string;
  preview?: string | null;
  created_at: string;
  updated_at: string;
};
type Session = { token: string; user: User };
type Features = { voice: boolean; translation: boolean; fraud?: boolean; external_calendar?: boolean; demo_auth: boolean; pipeline_stages: string[]; supported_languages?: string[]; language_options?: Array<{ label: string; code: string }> };
type LandingFeature = { title: string; short: string; detail: string; example: string; stage: string; tone: "blue" | "purple" | "orange" | "green" };
type DemoStep = { eyebrow: string; title: string; description: string; kind: "upload" | "scan" | "risk" | "action" };
type CalendarIntegration = { id: string; provider: string; calendar_id?: string | null; auto_sync: boolean; last_sync_at?: string | null; connected: boolean };
type NotificationItem = { id: string; title: string; body: string; channel: string; status: string; created_at: string };
type ReminderOptions = { channel: "in_app" | "email"; days_before: number };
type AuditItem = { id: string; user_id?: string; document_id?: string; action: string; created_at: string };

const DEFAULT_LANGUAGE = "English";

function readLanguage() {
  if (typeof window === "undefined") return DEFAULT_LANGUAGE;
  return window.localStorage.getItem("docuguardian_language") || DEFAULT_LANGUAGE;
}

function writeLanguage(language: string) {
  window.localStorage.setItem("docuguardian_language", language);
}

function languageOptions(features: Features | null) {
  return features?.supported_languages?.length ? features.supported_languages : [DEFAULT_LANGUAGE, "Spanish", "Hindi", "French", "German", "Arabic"];
}

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";

function readToken() { return typeof window === "undefined" ? "" : window.localStorage.getItem("docuguardian_token") || ""; }

async function apiFetch(path: string, token: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(`${API_URL}${path}`, { ...init, headers });
}

function greetingForNow() {
  const hour = new Date().getHours();
  if (hour < 12) return "Good morning";
  if (hour < 18) return "Good afternoon";
  return "Good evening";
}

export default function Home() {
  const [session, setSession] = useState<Session | null | undefined>(undefined);
  const [authView, setAuthView] = useState<"landing" | "auth">("landing");
  const [active, setActive] = useState<NavKey>("nav.dashboard");
  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [deadlines, setDeadlines] = useState<Deadline[]>([]);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [features, setFeatures] = useState<Features | null>(null);
  const [notifications, setNotifications] = useState<NotificationItem[]>([]);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [processing, setProcessing] = useState<{ name: string; progress: number; stage: string; stages: Stage[] } | null>(null);
  const [processingVisible, setProcessingVisible] = useState(false);
  const [loading, setLoading] = useState(false);
  const [toast, setToast] = useState("");
  const [language, setLanguage] = useState(DEFAULT_LANGUAGE);
  const { t, isRtl } = useTranslation(language);

  useEffect(() => { setLanguage(readLanguage()); }, []);

  useEffect(() => {
    if (typeof window === "undefined") return;
    const params = new URLSearchParams(window.location.search);
    const calendar = params.get("calendar");
    const provider = params.get("provider");
    if (calendar === "connected") setToast(t("settings.calendarConnected"));
    if (calendar === "failed") setToast(t("settings.calendarFailed"));
    if (calendar) {
      window.history.replaceState({}, "", window.location.pathname);
      if (provider) setActive("nav.settings");
    }
  }, [t]);

  useEffect(() => {
    fetch(`${API_URL}/api/v1/features`).then(async response => { if (response.ok) setFeatures(await response.json()); }).catch(() => undefined);
    const token = readToken();
    if (!token) { setSession(null); return; }
    apiFetch("/api/v1/auth/me", token).then(async response => {
      if (!response.ok) throw new Error("expired");
      setSession({ token, user: await response.json() });
    }).catch(() => { window.localStorage.removeItem("docuguardian_token"); setSession(null); });
  }, []);

  async function loadWorkspace(current = session) {
    if (!current) return;
    setLoading(true);
    try {
      const [documentsResponse, deadlinesResponse, analyticsResponse, notificationsResponse] = await Promise.all([
        apiFetch("/api/v1/documents", current.token),
        apiFetch("/api/v1/deadlines", current.token),
        apiFetch("/api/v1/analytics/overview", current.token),
        apiFetch("/api/v1/notifications", current.token),
      ]);
      if ([documentsResponse, deadlinesResponse, analyticsResponse].some(response => response.status === 401)) { signOut(); return; }
      if (documentsResponse.ok) setDocs(await documentsResponse.json());
      if (deadlinesResponse.ok) setDeadlines(await deadlinesResponse.json());
      if (analyticsResponse.ok) setAnalytics(await analyticsResponse.json());
      if (notificationsResponse.ok) setNotifications(await notificationsResponse.json());
    } finally { setLoading(false); }
  }

  useEffect(() => { if (session) loadWorkspace(session); }, [session]);
  useEffect(() => { if (!toast) return; const timer = window.setTimeout(() => setToast(""), 3200); return () => window.clearTimeout(timer); }, [toast]);

  function signOut() {
    window.localStorage.removeItem("docuguardian_token");
    setSession(null); setDocs([]); setDeadlines([]); setAnalytics(null); setNotifications([]); setAuthView("landing");
  }

  async function handleUpload(file?: File) {
    if (!file || !session) return;
    setUploadError("");
    const allowed = ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "image/png", "image/jpeg"];
    if (!allowed.includes(file.type) && !/\.(pdf|docx|png|jpe?g)$/i.test(file.name)) { setUploadError("Use a PDF, DOCX, PNG, or JPG file."); return; }
    if (file.size > 25 * 1024 * 1024) { setUploadError("Files must be 25 MB or smaller."); return; }
    setUploadOpen(false); setProcessing({ name: file.name, progress: 0, stage: "Uploading", stages: [] }); setProcessingVisible(true);
    const body = new FormData(); body.append("file", file);
    try {
      const response = await apiFetch("/api/v1/documents", session.token, { method: "POST", body });
      if (!response.ok) throw new Error((await response.json()).detail || "Upload failed");
      const created = await response.json();
      let finished = false;
      for (let attempt = 0; attempt < 240 && !finished; attempt++) {
        await new Promise(resolve => window.setTimeout(resolve, 500));
        const statusResponse = await apiFetch(`/api/v1/documents/${created.id}/processing`, session.token);
        if (!statusResponse.ok) throw new Error("Unable to read processing status");
        const status = await statusResponse.json();
        setProcessing({ name: file.name, progress: status.progress || 0, stage: status.stage || "Queued", stages: status.stages || [] });
        finished = status.status === "completed" || status.status === "failed";
      }
      if (!finished) throw new Error("Processing is taking longer than expected. Check the Documents screen for status.");
      await loadWorkspace(session);
      setToast("Document analysis complete.");
    } catch (error) { setUploadError(error instanceof Error ? error.message : "Upload failed"); }
    finally { setProcessing(null); setProcessingVisible(false); }
  }

  function onFileChange(event: ChangeEvent<HTMLInputElement>) { handleUpload(event.target.files?.[0]); event.target.value = ""; }
  function onDrop(event: DragEvent<HTMLDivElement>) { event.preventDefault(); handleUpload(event.dataTransfer.files?.[0]); }

  if (session === undefined) return <div className="loading-screen">{t("loadingWorkspace")}</div>;
  if (!session) {
    if (authView === "landing") return <LandingPage onSignIn={() => setAuthView("auth")} features={features} />;
    return <AuthScreen features={features} onBack={() => setAuthView("landing")} onAuthenticated={next => setSession(next)} />;
  }

  const currentPage = active === "nav.dashboard"
    ? <Dashboard docs={docs} deadlines={deadlines} analytics={analytics} loading={loading} t={t} onUpload={() => setUploadOpen(true)} onOpenDocuments={() => setActive("nav.documents")} onOpenChat={() => setActive("nav.chat")} onOpenCalendar={() => setActive("nav.calendar")} />
    : <WorkspaceScreen active={active} docs={docs} deadlines={deadlines} analytics={analytics} notifications={notifications} features={features} user={session.user} token={session.token} language={language} t={t} onLanguageChange={next => { writeLanguage(next); setLanguage(next); setToast(`${t("settings.languageChanged")} ${next}.`); }} onUpload={() => setUploadOpen(true)} onRefresh={() => loadWorkspace(session)} onToast={setToast} />;

  return <div className="app-shell" dir={isRtl ? "rtl" : "ltr"}>
    <aside className="sidebar"><div className="brand"><span className="brand-mark">D</span><span>DocuGuardian</span></div><div className="nav-label">{t("workspace")}</div><nav className="nav">{navKeys.map(([icon, key]) => <button key={key} className={active === key ? "active" : ""} onClick={() => setActive(key)}><span className="nav-icon">{icon}</span><span>{t(key)}</span></button>)}</nav><div className="sidebar-bottom"><div className="user"><span className="avatar">{initials(session.user.name)}</span><div><b>{session.user.name}</b><small>{session.user.role} · {session.user.email}</small></div></div><button className="signout" onClick={signOut}>{t("signOut")}</button></div></aside>
    <main className="main"><header className="topbar"><div className="crumb">{t("workspace")} / <strong>{t(active)}</strong></div><div className="top-actions">{notifications.length > 0 && <span className="bell" title={`${notifications.length} notifications`}>🔔</span>}<span className="avatar">{initials(session.user.name)}</span></div></header><section className="content">{currentPage}</section></main>
    {uploadOpen && <div className="upload-modal" role="dialog" aria-modal="true"><div className="modal"><div className="modal-head"><h2>{t("upload.title")}</h2><button className="close" onClick={() => setUploadOpen(false)} aria-label="Close">×</button></div><div className="drop" onDragOver={event => event.preventDefault()} onDrop={onDrop}><div className="drop-icon">↑</div><strong>{t("upload.dropTitle")}</strong><p>{t("upload.dropHint")}</p><label className="browse">{t("upload.browse")}<input type="file" accept=".pdf,.docx,.png,.jpg,.jpeg" onChange={onFileChange} /></label></div><div className="format">{t("upload.formats")}</div>{uploadError && <p className="form-error">{uploadError}</p>}</div></div>}
    {processing && processingVisible && <ProcessingModal processing={processing} onClose={() => setProcessingVisible(false)} />}
    {toast && <div className="toast">{toast}</div>}
  </div>;
}

function initials(name: string) { return name.split(/\s+/).map(part => part[0]).join("").slice(0, 2).toUpperCase(); }

function chatWelcome(hasDocument: boolean): ChatMessage {
  return {
    role: "ai",
    text: hasDocument
      ? "Ask a question about this analyzed document and I’ll cite retrieved evidence."
      : "Select an analyzed document to start a grounded conversation.",
  };
}

function mapApiChatMessage(row: { role: string; content: string; citations?: ChatMessage["citations"] }): ChatMessage {
  return {
    role: row.role === "assistant" ? "ai" : "user",
    text: row.content,
    citations: row.citations || undefined,
  };
}

function formatRelativeTime(iso: string) {
  const diff = Date.now() - new Date(iso).getTime();
  const minutes = Math.floor(diff / 60000);
  if (minutes < 1) return "Just now";
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  const days = Math.floor(hours / 24);
  if (days < 7) return `${days}d ago`;
  return new Date(iso).toLocaleDateString();
}

const LANDING_PIPELINE = ["OCR and parsing", "Classification", "Layout understanding", "Structured extraction", "Clause extraction", "Risk analysis", "Deadline detection", "Recommendations", "Embeddings", "Report generation"];

const LANDING_FEATURES: LandingFeature[] = [
  { title: "Plain-language summary", short: "Understand the important parts at a glance.", detail: "Turn dense clauses and formal language into a concise explanation of what the document means for you.", example: "You can cancel with 30 days’ notice, but the agreement renews automatically each year.", stage: "Report generation", tone: "blue" },
  { title: "Risk score 0–100", short: "See how much attention a document deserves.", detail: "A grounded score makes it easier to prioritize reviews across contracts, policies, and reports.", example: "72 / 100 · Review recommended before signing", stage: "Risk analysis", tone: "purple" },
  { title: "Hidden penalty detection", short: "Spot fees, liability, and unfavorable fine print.", detail: "Surface clauses that could create unexpected costs or obligations before they become a surprise.", example: "Early termination fee: 2 months of service charges", stage: "Clause extraction", tone: "orange" },
  { title: "Deadline reminders", short: "Never miss a renewal or notice window.", detail: "Extract important dates and turn them into a clear timeline you can act on.", example: "Renewal notice due · 14 Aug 2026", stage: "Deadline detection", tone: "green" },
  { title: "Grounded AI chat", short: "Ask questions and get evidence-backed answers.", detail: "Chat with an analyzed document and trace answers back to the source text that supports them.", example: "“What happens if I end this agreement early?” · Page 8", stage: "Embeddings", tone: "blue" },
  { title: "Multi-language translation", short: "Review insights in the language you prefer.", detail: "Translate summaries and extracted insights while keeping the original evidence in view.", example: "Summary translated to Spanish", stage: "Report generation", tone: "purple" },
  { title: "Voice summary", short: "Listen to the key points while you move.", detail: "Generate an audio overview of the document’s most important risks, dates, and next steps.", example: "2 min 18 sec · Ready to play", stage: "Report generation", tone: "green" },
  { title: "Contract comparison", short: "Make changes between two versions obvious.", detail: "Compare documents side by side to find added risks, changed clauses, and missing protections.", example: "3 changed clauses · 1 new risk", stage: "Structured extraction", tone: "orange" },
];

const DEMO_STEPS: DemoStep[] = [
  { eyebrow: "01 · Upload", title: "Start with the document you need to understand", description: "Drop in a contract, policy, report, or scanned document and DocuGuardian prepares it for review.", kind: "upload" },
  { eyebrow: "02 · Analyze", title: "Watch the document become structured insight", description: "The pipeline reads the layout, extracts clauses, and connects related evidence across the document.", kind: "scan" },
  { eyebrow: "03 · Understand risk", title: "See the clauses that need your attention", description: "A clear score and evidence-backed findings show what could cost you and why it matters.", kind: "risk" },
  { eyebrow: "04 · Take action", title: "Leave with a plan, not a pile of pages", description: "Deadlines and recommendations turn the analysis into practical next steps before you sign.", kind: "action" },
];

function pipelineDescription(stage: string) {
  const descriptions: Record<string, string> = {
    "OCR and parsing": "Reads text from digital files and scanned pages so every important detail can be analyzed.",
    Classification: "Identifies the document type and the kinds of obligations it contains.",
    "Layout understanding": "Preserves headings, tables, signatures, and page structure as context.",
    "Structured extraction": "Organizes parties, amounts, dates, and terms into useful fields.",
    "Clause extraction": "Separates individual clauses so risks and protections can be reviewed clearly.",
    "Risk analysis": "Scores potential exposure and explains the evidence behind each finding.",
    "Deadline detection": "Finds renewal, payment, expiry, and notice dates that may need action.",
    Recommendations: "Turns findings into specific review, negotiation, and follow-up actions.",
    Embeddings: "Connects your questions to the most relevant passages for grounded chat.",
    "Report generation": "Brings the analysis together in a readable report you can share and revisit.",
  };
  return descriptions[stage] || "Transforms document content into evidence-backed intelligence you can act on.";
}

function LandingPage({ onSignIn, features }: { onSignIn: () => void; features: Features | null }) {
  const [selectedFeature, setSelectedFeature] = useState<LandingFeature | null>(null);
  const [selectedStage, setSelectedStage] = useState("");
  const [demoOpen, setDemoOpen] = useState(false);
  const [demoStep, setDemoStep] = useState(0);
  const pipelineStages = features?.pipeline_stages?.length ? features.pipeline_stages : LANDING_PIPELINE;
  const activeStage = selectedStage || pipelineStages[0];

  useEffect(() => {
    if (!demoOpen) return;
    function closeOnEscape(event: KeyboardEvent) { if (event.key === "Escape") setDemoOpen(false); }
    window.addEventListener("keydown", closeOnEscape);
    return () => window.removeEventListener("keydown", closeOnEscape);
  }, [demoOpen]);

  function openDemo() { setDemoStep(0); setDemoOpen(true); }

  return <div className="landing">
    <div className="landing-hero">
      <div className="landing-brand"><span className="brand-mark">D</span><span>DocuGuardian</span></div>
      <h1>Protect Every Document Before It Costs You</h1>
      <p>Transform contracts, policies, and reports into risk scores, deadlines, and clear next actions—before you sign.</p>
      <div className="landing-cta"><button className="primary" onClick={onSignIn}>Get started <span aria-hidden="true">→</span></button><button className="ghost" onClick={openDemo}><span className="play-icon" aria-hidden="true">▶</span> Watch demo</button></div>
      <div className="landing-trust"><span><span className="trust-dot" aria-hidden="true">✓</span> Evidence-backed</span><span><span className="trust-dot" aria-hidden="true">✓</span> Built for clarity</span><span><span className="trust-dot" aria-hidden="true">✓</span> Ready before you sign</span></div>
    </div>
    <div className="landing-grid" aria-label="Product capabilities">
      {LANDING_FEATURES.map((feature, index) => <button className={`landing-feature ${selectedFeature?.title === feature.title ? "selected" : ""}`} data-tone={feature.tone} key={feature.title} onClick={() => setSelectedFeature(selectedFeature?.title === feature.title ? null : feature)} aria-expanded={selectedFeature?.title === feature.title} aria-controls="landing-feature-preview">
        <span className="feature-number">0{index + 1}</span><span className="feature-arrow" aria-hidden="true">↗</span><strong>{feature.title}</strong><span>{feature.short}</span>
      </button>)}
    </div>
    {selectedFeature && <section className="landing-feature-preview" id="landing-feature-preview" aria-live="polite">
      <div className={`feature-preview-icon ${selectedFeature.tone}`} aria-hidden="true">✦</div><div className="feature-preview-copy"><div className="preview-kicker">Feature preview <span>·</span> {selectedFeature.stage}</div><h2>{selectedFeature.title}</h2><p>{selectedFeature.detail}</p><div className="preview-example"><span className="example-label">Example output</span><strong>{selectedFeature.example}</strong></div><button className="primary" onClick={onSignIn}>Try it with your document <span aria-hidden="true">→</span></button></div><button className="preview-close" onClick={() => setSelectedFeature(null)} aria-label="Close feature preview">×</button>
    </section>}
    <section className="landing-pipeline" aria-labelledby="pipeline-title">
      <div className="pipeline-heading"><div><span className="eyebrow">How it works</span><h2 id="pipeline-title">From upload to confident action</h2></div><span className="pipeline-live"><span aria-hidden="true" /> Live pipeline</span></div>
      <div className="pipeline-track">{pipelineStages.map((stage, index) => <button className={`pipeline-stage ${activeStage === stage ? "active" : ""}`} key={stage} onClick={() => setSelectedStage(stage)} aria-pressed={activeStage === stage}><span className="pipeline-index">{String(index + 1).padStart(2, "0")}</span><span>{stage}</span>{index < pipelineStages.length - 1 && <span className="pipeline-connector" aria-hidden="true">→</span>}</button>)}</div>
      <div className="pipeline-detail"><div className="pipeline-detail-icon" aria-hidden="true">{String(Math.max(1, pipelineStages.indexOf(activeStage) + 1)).padStart(2, "0")}</div><div><span className="preview-kicker">Selected stage</span><h3>{activeStage}</h3><p>{pipelineDescription(activeStage)}</p></div><button className="pipeline-demo-link" onClick={openDemo}>See it in the demo <span aria-hidden="true">→</span></button></div>
    </section>
    <p className="landing-note">Your documents stay at the center—from OCR and parsing to recommendations and a report you can trust.</p>
    {demoOpen && <div className="demo-modal-backdrop" role="presentation" onMouseDown={event => { if (event.target === event.currentTarget) setDemoOpen(false); }}><div className="demo-modal" role="dialog" aria-modal="true" aria-labelledby="demo-title"><div className="demo-modal-head"><div><span className="eyebrow">Interactive product tour</span><h2 id="demo-title">See how DocuGuardian protects a document</h2></div><button className="preview-close" onClick={() => setDemoOpen(false)} aria-label="Close demo">×</button></div><div className="demo-progress"><div><span>Step {demoStep + 1} of {DEMO_STEPS.length}</span><strong>{Math.round(((demoStep + 1) / DEMO_STEPS.length) * 100)}%</strong></div><div className="demo-progress-track"><span style={{ width: `${((demoStep + 1) / DEMO_STEPS.length) * 100}%` }} /></div></div><div className="demo-content"><div className={`demo-visual demo-${DEMO_STEPS[demoStep].kind}`} aria-hidden="true">{DEMO_STEPS[demoStep].kind === "upload" && <><div className="demo-file-icon">PDF</div><strong>Supplier agreement.pdf</strong><span>12 pages · 2.4 MB</span><div className="demo-upload-line"><span>Drop to analyze</span><span>↥</span></div></>}{DEMO_STEPS[demoStep].kind === "scan" && <><div className="demo-scan-file"><span /><span /><span /><span /><span /></div><div className="demo-scan-beam" /><div className="demo-scan-status"><span className="demo-spinner" /> Analyzing page 8 of 12</div></>}{DEMO_STEPS[demoStep].kind === "risk" && <><div className="demo-score"><strong>72</strong><span>/100 risk score</span></div><div className="demo-risk-row"><span className="risk-dot high" /><div><strong>Early termination fee</strong><span>High attention · Page 8</span></div></div><div className="demo-risk-row"><span className="risk-dot medium" /><div><strong>Auto-renewal clause</strong><span>Review recommended</span></div></div></>}{DEMO_STEPS[demoStep].kind === "action" && <><div className="demo-action-card"><span>Next deadline</span><strong>14 Aug 2026</strong><small>Renewal notice due</small></div><div className="demo-check-row"><span>✓</span><strong>Review termination clause</strong></div><div className="demo-check-row"><span>○</span><strong>Set a calendar reminder</strong></div></>}</div><div className="demo-copy"><span className="eyebrow">{DEMO_STEPS[demoStep].eyebrow}</span><h3>{DEMO_STEPS[demoStep].title}</h3><p>{DEMO_STEPS[demoStep].description}</p>{demoStep === DEMO_STEPS.length - 1 && <button className="primary" onClick={onSignIn}>Get started <span aria-hidden="true">→</span></button>}</div></div><div className="demo-dots">{DEMO_STEPS.map((step, index) => <button key={step.eyebrow} className={index === demoStep ? "active" : ""} onClick={() => setDemoStep(index)} aria-label={`Go to demo step ${index + 1}`} />)}</div><div className="demo-actions"><button className="ghost" onClick={() => setDemoStep(step => Math.max(0, step - 1))} disabled={demoStep === 0}>← Back</button>{demoStep < DEMO_STEPS.length - 1 ? <button className="primary" onClick={() => setDemoStep(step => Math.min(DEMO_STEPS.length - 1, step + 1))}>Next <span aria-hidden="true">→</span></button> : <button className="ghost" onClick={() => setDemoStep(0)}>Replay demo</button>}</div></div></div>}
  </div>;
}

function AuthScreen({ onAuthenticated, onBack, features }: { onAuthenticated: (session: Session) => void; onBack: () => void; features: Features | null }) {
  const [mode, setMode] = useState<"login" | "register">("login");
  const [name, setName] = useState(""); const [email, setEmail] = useState(""); const [password, setPassword] = useState(""); const [error, setError] = useState(""); const [busy, setBusy] = useState(false);
  async function submit(event: FormEvent) {
    event.preventDefault(); setBusy(true); setError("");
    try {
      const response = await fetch(`${API_URL}/api/v1/auth/${mode === "login" ? "login" : "register"}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(mode === "login" ? { email, password } : { name, email, password }) });
      const data = await response.json(); if (!response.ok) throw new Error(data.detail || "Unable to authenticate");
      window.localStorage.setItem("docuguardian_token", data.access_token); onAuthenticated({ token: data.access_token, user: data.user });
    } catch (submitError) { setError(submitError instanceof Error ? submitError.message : "Unable to authenticate"); } finally { setBusy(false); }
  }
  async function demo() {
    const response = await fetch(`${API_URL}/api/v1/auth/demo`, { method: "POST" }); if (!response.ok) { setError("Demo access is disabled."); return; }
    const data = await response.json(); window.localStorage.setItem("docuguardian_token", data.access_token); onAuthenticated({ token: data.access_token, user: data.user });
  }
  return <div className="auth-shell"><div className="auth-card card"><button className="text-button back-link" onClick={onBack}>← Back</button><div className="brand auth-brand"><span className="brand-mark">D</span><span>DocuGuardian</span></div><h1>{mode === "login" ? "Welcome back" : "Create your workspace"}</h1><p className="auth-subtitle">Understand important documents before they become problems.</p><form onSubmit={submit}>{mode === "register" && <label>Name<input value={name} onChange={event => setName(event.target.value)} required minLength={2} /></label>}<label>Email<input type="email" value={email} onChange={event => setEmail(event.target.value)} required /></label><label>Password<input type="password" value={password} onChange={event => setPassword(event.target.value)} required minLength={8} /></label>{error && <p className="form-error">{error}</p>}<button className="primary auth-submit" disabled={busy}>{busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}</button></form><button className="text-button" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}>{mode === "login" ? "Create a new account" : "Already have an account? Sign in"}</button>{features?.demo_auth !== false && <button className="demo-button" onClick={demo}>Use local demo account</button>}</div></div>;
}

function Dashboard({ docs, deadlines, analytics, loading, t, onUpload, onOpenDocuments, onOpenChat, onOpenCalendar }: { docs: DocumentItem[]; deadlines: Deadline[]; analytics: Analytics | null; loading: boolean; t: (key: MessageKey) => string; onUpload: () => void; onOpenDocuments: () => void; onOpenChat: () => void; onOpenCalendar: () => void }) {
  const protection = analytics?.protection_score ?? (analytics ? Math.max(0, 100 - analytics.average_risk_score) : 0);
  const greeting = greetingForNow() === "Good morning" ? t("dashboard.greetingMorning") : greetingForNow() === "Good afternoon" ? t("dashboard.greetingAfternoon") : t("dashboard.greetingEvening");
  return <><div className="intro"><div><h1>{greeting}</h1><p>{t("dashboard.subtitle")}</p></div><button className="primary" onClick={onUpload}>＋ {t("uploadDocument")}</button></div><div className="stats"><Stat icon="▤" label={t("stat.documents")} value={analytics ? String(analytics.documents_uploaded) : "—"} foot={t("stat.foot.documents")} /><Stat icon="!" label={t("stat.highRisk")} value={analytics ? String(analytics.high_risk_documents) : "—"} foot={t("stat.foot.highRisk")} tone="red" /><Stat icon="◷" label={t("stat.deadlines")} value={analytics ? String(analytics.upcoming_deadlines) : "—"} foot={t("stat.foot.deadlines")} tone="orange" /><Stat icon="⚠" label={t("stat.fraudFlags")} value={analytics ? String(analytics.fraud_flagged_documents ?? 0) : "—"} foot={t("stat.foot.fraud")} tone="orange" /><Stat icon="✓" label={t("stat.protection")} value={analytics ? `${protection}%` : "—"} foot={t("stat.foot.protection")} tone="green" /></div>{loading ? <EmptyState title={t("dashboard.loadingTitle")} text={t("dashboard.loadingHint")} /> : <div className="grid"><div className="card docs"><div className="panel-head"><h2>{t("dashboard.recentDocuments")}</h2><button className="view" onClick={onOpenDocuments}>{t("dashboard.viewAll")}</button></div>{docs.length ? docs.slice(0, 6).map(doc => <div className="doc-row" key={doc.id}><DocumentRow doc={doc} /></div>) : <EmptyState title={t("dashboard.noDocuments")} text={t("dashboard.noDocumentsHint")} action={onUpload} actionLabel={t("uploadDocument")} />}</div><div><div className="card deadline"><div className="panel-head"><h2>{t("dashboard.upcomingDeadlines")}</h2><button className="view" onClick={onOpenCalendar}>{t("dashboard.openCalendar")}</button></div>{deadlines.length ? deadlines.slice(0, 5).map(deadline => <DeadlineRow key={deadline.id} deadline={deadline} />) : <EmptyState title={t("dashboard.noDeadlines")} text={t("dashboard.noDeadlinesHint")} />}</div><div className="insight"><h3>{t("dashboard.insightTitle")}</h3><p>{t("dashboard.insightBody")}</p><button onClick={onOpenChat}>{t("dashboard.insightCta")}</button></div></div></div>}</>;
}

function WorkspaceScreen({ active, docs, deadlines, analytics, notifications, features, user, token, language, t, onLanguageChange, onUpload, onRefresh, onToast }: { active: NavKey; docs: DocumentItem[]; deadlines: Deadline[]; analytics: Analytics | null; notifications: NotificationItem[]; features: Features | null; user: User; token: string; language: string; t: (key: MessageKey) => string; onLanguageChange: (language: string) => void; onUpload: () => void; onRefresh: () => void; onToast: (message: string) => void }) {
  const [report, setReport] = useState<Report | null>(null);
  const [reportDoc, setReportDoc] = useState<DocumentItem | null>(null);
  const [question, setQuestion] = useState("");
  const [selectedChatDoc, setSelectedChatDoc] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const [sessions, setSessions] = useState<ChatSessionItem[]>([]);
  const [activeSessionId, setActiveSessionId] = useState<string | null>(null);
  const [sessionsLoading, setSessionsLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [compareIds, setCompareIds] = useState(["", ""]);
  const [comparison, setComparison] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");
  const [audit, setAudit] = useState<AuditItem[]>([]);
  const analyzedDocs = docs.filter(doc => doc.status === "completed");
  const prompts = useMemo(() => {
    const doc = analyzedDocs.find(item => item.id === selectedChatDoc);
    const name = doc?.name;
    const base = name ? [`Summarize risks in ${name}`, `What deadlines matter in ${name}?`] : ["Summarize the key risks", "What deadlines should I track?"];
    return [...base, "Explain this like I’m 15", "What should I negotiate next?"];
  }, [analyzedDocs, selectedChatDoc]);
  const showStarterPrompts = !messages.some(message => message.role === "user") && !chatLoading;

  useEffect(() => {
    if (!selectedChatDoc && analyzedDocs[0]) setSelectedChatDoc(analyzedDocs[0].id);
    if (!compareIds[0] && analyzedDocs[0]) setCompareIds([analyzedDocs[0].id, analyzedDocs[1]?.id || analyzedDocs[0].id]);
  }, [analyzedDocs, selectedChatDoc, compareIds]);

  useEffect(() => {
    if (active !== "nav.chat") return;
    if (messages.length === 0) setMessages([chatWelcome(!!selectedChatDoc)]);
  }, [active, selectedChatDoc, messages.length]);

  useEffect(() => {
    if (active !== "nav.chat") return;
    loadSessions().catch(() => undefined);
  }, [active, token]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, chatLoading]);

  useEffect(() => {
    if (active !== "nav.settings") return;
    apiFetch("/api/v1/audit", token).then(async response => { if (response.ok) setAudit(await response.json()); }).catch(() => undefined);
  }, [active, token]);

  useEffect(() => {
    if (active !== "nav.documents" || reportDoc) return;
    const firstCompleted = docs.find(doc => doc.status === "completed");
    if (firstCompleted) openReport(firstCompleted);
  }, [active, docs, reportDoc]);

  async function loadSessions() {
    setSessionsLoading(true);
    try {
      const response = await apiFetch("/api/v1/chat/sessions", token);
      if (response.ok) setSessions(await response.json());
    } finally {
      setSessionsLoading(false);
    }
  }

  function handleDocumentChange(documentId: string) {
    setSelectedChatDoc(documentId);
    setActiveSessionId(null);
    setMessages([chatWelcome(!!documentId)]);
    setError("");
  }

  async function createNewChat() {
    if (!selectedChatDoc) {
      onToast("Select an analyzed document first.");
      return;
    }
    setError("");
    const response = await apiFetch("/api/v1/chat/sessions", token, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ document_id: selectedChatDoc }),
    });
    if (!response.ok) {
      onToast("Unable to start a new chat.");
      return;
    }
    const session = await response.json();
    setActiveSessionId(session.id);
    setMessages([chatWelcome(true)]);
    await loadSessions();
  }

  async function selectSession(sessionId: string) {
    if (sessionId === activeSessionId || chatLoading) return;
    setError("");
    setChatLoading(true);
    try {
      const session = sessions.find(item => item.id === sessionId);
      const response = await apiFetch(`/api/v1/chat/sessions/${sessionId}/messages`, token);
      if (!response.ok) {
        setError("Unable to load this chat.");
        return;
      }
      const rows = await response.json();
      setActiveSessionId(sessionId);
      if (session) setSelectedChatDoc(session.document_id);
      setMessages(rows.length ? rows.map(mapApiChatMessage) : [chatWelcome(!!session?.document_id)]);
    } finally {
      setChatLoading(false);
    }
  }

  async function deleteSession(sessionId: string) {
    const response = await apiFetch(`/api/v1/chat/sessions/${sessionId}`, token, { method: "DELETE" });
    if (!response.ok) {
      onToast("Unable to delete chat.");
      return;
    }
    if (activeSessionId === sessionId) {
      setActiveSessionId(null);
      setMessages([chatWelcome(!!selectedChatDoc)]);
    }
    await loadSessions();
  }

  async function openReport(doc: DocumentItem) {
    setError("");
    const response = await apiFetch(`/api/v1/documents/${doc.id}/report`, token);
    if (!response.ok) { setError("The report is not ready yet."); return; }
    setReport(await response.json()); setReportDoc(doc);
  }

  async function ask(text = question) {
    if (!text.trim() || !selectedChatDoc || chatLoading) return;
    setQuestion(""); setError("");
    setMessages(items => [...items, { role: "user", text }]);
    setChatLoading(true);
    try {
      const response = await apiFetch(`/api/v1/documents/${selectedChatDoc}/chat`, token, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: text, target_language: features?.translation ? language : undefined, session_id: activeSessionId || undefined }) });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        const detail = payload?.detail;
        setError(typeof detail === "string" ? detail : "Chat is unavailable for this document.");
        setMessages(items => items.slice(0, -1));
        return;
      }
      const answer = await response.json();
      if (answer.session_id) setActiveSessionId(answer.session_id);
      setMessages(items => [...items, {
        role: "ai",
        text: answer.answer,
        citations: answer.citations,
        suggestedPrompts: answer.suggested_prompts,
      }]);
      await loadSessions();
    } catch {
      setError("Unable to reach the API. Restart the backend and try again.");
      setMessages(items => items.slice(0, -1));
    } finally {
      setChatLoading(false);
    }
  }

  async function compare() {
    if (!compareIds[0] || !compareIds[1]) return;
    const response = await apiFetch("/api/v1/comparisons", token, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ document_a_id: compareIds[0], document_b_id: compareIds[1] }) });
    if (response.ok) setComparison(await response.json());
    else { setComparison(null); onToast(t("compare.failed")); }
  }

  async function remind(id: string, options: ReminderOptions) {
    const response = await apiFetch(`/api/v1/deadlines/${id}/reminders`, token, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(options) });
    if (response.ok) { onToast("Reminder scheduled."); onRefresh(); }
    else onToast("Unable to schedule reminder.");
  }

  async function removeDoc(id: string) {
    const response = await apiFetch(`/api/v1/documents/${id}`, token, { method: "DELETE" });
    if (response.ok || response.status === 204) { onToast("Document deleted."); if (reportDoc?.id === id) { setReport(null); setReportDoc(null); } onRefresh(); }
  }

  async function retryDoc(id: string) {
    const response = await apiFetch(`/api/v1/documents/${id}/retry`, token, { method: "POST" });
    if (response.ok) { onToast("Document queued for re-analysis."); onRefresh(); }
  }

  const pageMeta = pageMetaKeys[active];
  const title = t(pageMeta.title);
  const subtitle = t(pageMeta.subtitle);

  return <>
    <div className={`workspace-head${active === "nav.chat" ? " workspace-head-compact" : ""}`}><div><h1>{title}</h1>{active !== "nav.chat" && <p>{subtitle}</p>}</div>{active === "nav.documents" && <button className="primary" onClick={onUpload}>＋ {t("uploadDocument")}</button>}</div>
    {error && <p className="form-error">{error}</p>}
    {active === "nav.documents" && <div className="workspace-grid"><div className="card workspace-card"><h2>{t("documents.all")} <span className="muted-count">({docs.length})</span></h2>{docs.length ? docs.map(doc => <div className="doc-row" key={doc.id}><DocumentRow doc={doc} compact /><div className="doc-actions"><button className="btn btn-secondary btn-report" onClick={() => openReport(doc)} disabled={doc.status !== "completed"}>{doc.status === "completed" ? t("documents.viewReport") : t("documents.report")}</button>{(doc.status === "failed" || doc.status === "completed") && <button className="btn btn-outline" onClick={() => retryDoc(doc.id)}>{t("documents.retry")}</button>}<button className="btn btn-danger" onClick={() => removeDoc(doc.id)}>{t("documents.delete")}</button></div></div>) : <EmptyState title={t("documents.empty")} text={t("documents.emptyHint")} action={onUpload} actionLabel={t("uploadDocument")} />}</div><ReportPanel report={report} reportDoc={reportDoc} token={token} features={features} language={language} languages={languageOptions(features)} t={t} onToast={onToast} /></div>}
    {active === "nav.chat" && <div className="chat-page"><div className="chat-shell">
      <div className="card chat-history">
        <button className="chat-new-btn primary" onClick={createNewChat} disabled={chatLoading || !selectedChatDoc}>＋ New chat</button>
        <div className="chat-history-list">
          {sessionsLoading && sessions.length === 0 ? <p className="chat-history-empty">Loading chats…</p> : null}
          {!sessionsLoading && sessions.length === 0 ? <p className="chat-history-empty">No chats yet. Start a new conversation.</p> : null}
          {sessions.map(session => <button
            key={session.id}
            className={`chat-session-item${activeSessionId === session.id ? " chat-session-active" : ""}`}
            onClick={() => selectSession(session.id)}
            disabled={chatLoading}
          >
            <span className="chat-session-title">{session.title}</span>
            <span className="chat-session-doc">{session.document_name}</span>
            {session.preview ? <span className="chat-session-preview">{session.preview}</span> : null}
            <span className="chat-session-meta">{formatRelativeTime(session.updated_at)}</span>
            <span
              className="chat-session-delete"
              role="button"
              tabIndex={0}
              aria-label="Delete chat"
              onClick={event => { event.stopPropagation(); deleteSession(session.id); }}
              onKeyDown={event => { if (event.key === "Enter") { event.stopPropagation(); deleteSession(session.id); } }}
            >×</span>
          </button>)}
        </div>
      </div>
      <div className="card chat-box">
        <div className="chat-toolbar">
          <label>Document<select value={selectedChatDoc} onChange={event => handleDocumentChange(event.target.value)} disabled={chatLoading}><option value="">Select an analyzed document</option>{analyzedDocs.map(doc => <option key={doc.id} value={doc.id}>{doc.name}</option>)}</select></label>
          {features?.translation && <label>{t("chat.responseLanguage")}<LanguageSelect value={language} languages={languageOptions(features)} onChange={onLanguageChange} disabled={chatLoading} /></label>}
        </div>
        <div className="messages">
          {showStarterPrompts ? <div className="chat-empty-state">
            <div className="chat-empty-icon" aria-hidden="true">✦</div>
            <h3>{selectedChatDoc ? "What would you like to know?" : "Select a document to begin"}</h3>
            <p>{selectedChatDoc ? "Ask anything about your analyzed document. Answers include source citations from the file." : "Choose an analyzed document above, then pick a suggested prompt or type your question."}</p>
            {selectedChatDoc ? <div className="chat-starter-prompts">{prompts.map(prompt => <button className="chat-starter-prompt" key={prompt} onClick={() => ask(prompt)} disabled={chatLoading}>{prompt}</button>)}</div> : null}
          </div> : <>
            {messages.map((message, index) => <ChatMessageBubble key={index} message={message} onSuggestedPrompt={ask} disabled={chatLoading || !selectedChatDoc} />)}
            {chatLoading && <ChatTypingIndicator />}
          </>}
          <div ref={messagesEndRef} />
        </div>
        <div className="chat-composer">
          <div className="chat-input"><input value={question} onChange={event => setQuestion(event.target.value)} onKeyDown={event => event.key === "Enter" && !chatLoading && ask()} placeholder={chatLoading ? "Waiting for response…" : "Ask about your documents…"} disabled={chatLoading || !selectedChatDoc} /><button className={`primary ${chatLoading ? "loading" : ""}`} onClick={() => ask()} disabled={chatLoading || !selectedChatDoc || !question.trim()}>{chatLoading ? "Thinking…" : "Send"}</button></div>
          <p className="chat-disclaimer">Decision support only. Confirm important decisions with a qualified professional.</p>
        </div>
      </div>
    </div></div>}
    {active === "nav.calendar" && <CalendarScreen deadlines={deadlines} onRemind={remind} onRefresh={onRefresh} notifications={notifications} />}
    {active === "nav.compare" && <ComparisonScreen docs={analyzedDocs} compareIds={compareIds} setCompareIds={setCompareIds} compare={compare} comparison={comparison} t={t} />}
    {active === "nav.analytics" && <AnalyticsScreen analytics={analytics} t={t} />}
    {active === "nav.settings" && <SettingsScreen user={user} features={features} audit={audit} notifications={notifications} language={language} languages={languageOptions(features)} token={token} t={t} onLanguageChange={onLanguageChange} onToast={onToast} />}
  </>;
}

function ReportPanel({ report, reportDoc, token, features, language, languages, t, onToast }: { report: Report | null; reportDoc: DocumentItem | null; token: string; features: Features | null; language: string; languages: string[]; t: (key: MessageKey) => string; onToast: (message: string) => void }) {
  const [translatedReport, setTranslatedReport] = useState<Report | null>(null);
  const [translating, setTranslating] = useState(false);
  const [downloadLanguage, setDownloadLanguage] = useState(language);
  const [pdfLoading, setPdfLoading] = useState(false);
  const [jsonLoading, setJsonLoading] = useState(false);
  const [voiceLoading, setVoiceLoading] = useState(false);
  const [voiceUrl, setVoiceUrl] = useState<string | null>(null);
  const [voiceLanguage, setVoiceLanguage] = useState(language);
  const [voiceGeneratedLanguage, setVoiceGeneratedLanguage] = useState<string | null>(null);
  const audioRef = useRef<HTMLAudioElement>(null);

  useEffect(() => {
    setTranslatedReport(null);
    setVoiceUrl(null);
    setVoiceGeneratedLanguage(null);
    setDownloadLanguage(language);
    setVoiceLanguage(language);
  }, [reportDoc?.id, language]);

  useEffect(() => () => { if (voiceUrl) URL.revokeObjectURL(voiceUrl); }, [voiceUrl]);

  useEffect(() => {
    setVoiceUrl(previous => {
      if (previous) URL.revokeObjectURL(previous);
      return null;
    });
    setVoiceGeneratedLanguage(null);
  }, [voiceLanguage]);

  if (!report || !reportDoc) return <div className="card workspace-card"><h2>{t("report.title")}</h2><p className="report-summary">{t("report.empty")}</p>{features?.voice ? <p className="voice-empty-hint">{t("report.emptyVoiceHint")}</p> : null}</div>;
  const activeReport = report;
  const activeDoc = reportDoc;
  const displayedReport = translatedReport || activeReport;
  const voiceReady = Boolean(voiceUrl && voiceGeneratedLanguage === voiceLanguage);

  async function downloadReport(format: "pdf" | "json") {
    const loading = format === "pdf" ? setPdfLoading : setJsonLoading;
    loading(true);
    try {
      const params = new URLSearchParams({ format, target_language: downloadLanguage });
      const response = await apiFetch(`/api/v1/documents/${activeDoc.id}/report/download?${params.toString()}`, token);
      if (!response.ok) { onToast(format === "pdf" ? "Unable to generate PDF report." : "Unable to download JSON report."); return; }
      const blob = await response.blob();
      const url = URL.createObjectURL(blob);
      const link = document.createElement("a");
      const extension = format === "pdf" ? "pdf" : "json";
      link.href = url;
      link.download = `${activeDoc.name.replace(/\.[^.]+$/, "")}-report.${extension}`;
      link.click();
      URL.revokeObjectURL(url);
      if (format === "pdf") onToast(`${t("report.pdfReady")} (${downloadLanguage}).`);
    } finally {
      loading(false);
    }
  }

  async function translateReport() {
    if (!features?.translation) return;
    setTranslating(true);
    try {
      const response = await apiFetch(`/api/v1/documents/${activeDoc.id}/translate`, token, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ target_language: language }) });
      if (!response.ok) { onToast("Translation is unavailable."); return; }
      const data = await response.json(); setTranslatedReport(data.report as Report); onToast(`Full report translated to ${language}.`);
    } finally {
      setTranslating(false);
    }
  }

  async function updateAction(item: ActionItem, completed: boolean) {
    if (!item.id) { onToast("This action item needs a fresh report before it can be saved."); return; }
    const response = await apiFetch(`/api/v1/action-items/${item.id}`, token, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: completed ? "completed" : "open" }),
    });
    if (!response.ok) { onToast("Unable to update action item."); return; }
    const updated = await response.json();
    const updateReport = (current: Report): Report => ({
      ...current,
      action_plan: current.action_plan?.map(action => action.id === item.id ? { ...action, status: updated.status } : action),
    });
    if (translatedReport) setTranslatedReport(updateReport(translatedReport));
    else if (report) setTranslatedReport(updateReport(report));
    onToast(completed ? "Action marked complete." : "Action reopened.");
  }

  async function playVoice() {
    if (voiceLoading) return;
    setVoiceLoading(true);
    try {
      const response = await apiFetch("/api/v1/voice-summary", token, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text: displayedReport.summary, target_language: voiceLanguage }),
      });
      if (!response.ok) { onToast("Voice summary is unavailable."); return; }
      const blob = await response.blob();
      const spokenLanguage = response.headers.get("X-Voice-Language") || voiceLanguage;
      const url = URL.createObjectURL(blob);
      setVoiceUrl(previous => {
        if (previous) URL.revokeObjectURL(previous);
        return url;
      });
      setVoiceGeneratedLanguage(voiceLanguage);
      onToast(`Voice summary ready (${spokenLanguage}).`);
      window.setTimeout(() => audioRef.current?.play().catch(() => onToast("Unable to play audio in this browser.")), 0);
    } finally {
      setVoiceLoading(false);
    }
  }

  return <div className="card workspace-card report-panel">
    <div className="report-header"><h2>{activeDoc.name}</h2><div className="doc-actions">{features?.translation && <button className="btn btn-secondary" onClick={translateReport} disabled={translating}>{translating ? t("report.translating") : `${t("report.translate")} ${language}`}</button>}</div></div>
    <div className="metric"><strong>{activeReport.risk_score}</strong><small>{activeReport.risk_level} risk · {activeReport.classification} · confidence {Math.round(activeReport.confidence * 100)}%</small></div>
    {features?.translation && <div className="language-note">{t("report.languageNote")} <strong>{language}</strong></div>}
    <div className="export-report-panel">
      <h3>{t("report.exportTitle")}</h3>
      <p className="muted">{t("report.exportDesc")}</p>
      <label className="export-language-label">{t("report.downloadLanguage")}<LanguageSelect value={downloadLanguage} languages={languages} onChange={setDownloadLanguage} disabled={pdfLoading || jsonLoading} /></label>
      <button className="primary report-generate-btn" onClick={() => downloadReport("pdf")} disabled={pdfLoading || jsonLoading}>{pdfLoading ? t("report.generatingPdf") : `${t("report.generatePdf")} (${downloadLanguage})`}</button>
      {pdfLoading ? <p className="report-generating-status">{t("report.generatingPdf")}</p> : null}
      <div className="report-action-row"><button className="btn btn-outline" onClick={() => downloadReport("json")} disabled={pdfLoading || jsonLoading}>{jsonLoading ? t("report.generatingPdf") : t("report.downloadJson")}</button></div>
    </div>
    <p className="report-summary">{displayedReport.summary}</p>
    {features?.voice && <div className="voice-summary-panel"><h3>{t("report.voice")}</h3><p className="muted">{t("report.voiceDesc")}</p><label className="voice-language-label">{t("report.voiceLanguage")}<LanguageSelect value={voiceLanguage} languages={languages} onChange={setVoiceLanguage} disabled={voiceLoading} /></label>{voiceReady ? <><audio ref={audioRef} className="voice-player" controls src={voiceUrl!} /><div className="report-action-row"><button className="btn btn-outline voice-regenerate-link" onClick={playVoice} disabled={voiceLoading}>{voiceLoading ? t("report.voiceGenerating") : t("report.voiceRegenerate")}</button></div></> : <button className="primary report-generate-btn" onClick={playVoice} disabled={voiceLoading}>{voiceLoading ? t("report.voiceGenerating") : `${t("report.voiceGenerate")} (${voiceLanguage})`}</button>}{voiceLoading ? <p className="report-generating-status">{t("report.voiceGenerating")}</p> : null}</div>}
    {translatedReport && <div className="translation-panel"><h3>{t("report.translate")} ({language})</h3><p className="report-summary">{t("report.translatedPanel")}</p></div>}
    <h3>{t("report.keyDetails")}</h3>
    {displayedReport.entities?.length ? displayedReport.entities.map((entity, index) => <div className="finding" key={`entity-${index}`}><div className="finding-top"><strong>{entity.label}</strong><span className="pill low">{entity.value}</span></div><div className="citation">{entity.page ? `page ${entity.page}` : ""}{entity.text_span ? ` · “${entity.text_span}”` : ""}{entity.confidence ? ` · ${Math.round(entity.confidence * 100)}% confidence` : ""}</div></div>) : <p className="muted">{t("report.noEntities")}</p>}
    <h3>{t("report.riskAnalysis")}</h3>
    {displayedReport.risks.length ? displayedReport.risks.map((risk, index) => <div className="finding" key={`${risk.title}-${index}`}><div className="finding-top"><strong>{risk.title}{risk.is_penalty ? " · penalty" : ""}</strong><span className={`pill ${risk.severity}`}>{risk.severity}</span></div><p>{risk.explanation}</p><small>{risk.recommendation}</small><div className="citation">{risk.source}{risk.page ? ` · page ${risk.page}` : ""}{risk.text_span ? ` · “${risk.text_span}”` : ""}{risk.confidence ? ` · ${Math.round(risk.confidence * 100)}% confidence` : ""}</div></div>) : <p className="muted">{t("report.noRisks")}</p>}
    {!!displayedReport.hidden_penalties?.length && <><h3>{t("report.hiddenPenalties")}</h3>{displayedReport.hidden_penalties.map((risk, index) => <div className="finding" key={`penalty-${index}`}><div className="finding-top"><strong>{risk.title}</strong><span className={`pill ${risk.severity}`}>{risk.severity}</span></div><p>{risk.explanation}</p></div>)}</>}
    {!!displayedReport.clauses?.length && <><h3>{t("report.clauses")}</h3>{displayedReport.clauses.map((clause, index) => <div className="finding" key={`clause-${index}`}><div className="finding-top"><strong>{clause.title}</strong><span className={`pill ${clause.severity}`}>{clause.severity}</span></div><p>{clause.body}</p><div className="citation">{clause.category}{clause.page ? ` · page ${clause.page}` : ""}{clause.text_span ? ` · “${clause.text_span}”` : ""}</div></div>)}</>}
    <h3>{t("report.obligations")}</h3>
    {displayedReport.obligations?.length ? displayedReport.obligations.map((item, index) => <div className="finding" key={`obligation-${index}`}><div className="finding-top"><strong>{item.title}</strong><span className={`pill ${item.severity}`}>{item.severity}</span></div><p>{item.description}</p><div className="citation">{t("report.party")}: {item.party}{item.due_date ? ` · due ${formatDate(item.due_date)}` : ""}{item.page ? ` · page ${item.page}` : ""}{item.text_span ? ` · “${item.text_span}”` : ""}</div></div>) : <p className="muted">{t("report.noObligations")}</p>}
    {features?.fraud !== false && <><h3 className="fraud-heading">{t("report.fraudIndicators")}</h3><p className="fraud-disclaimer">{t("report.fraudDisclaimer")}</p>{displayedReport.fraud_indicators?.length ? displayedReport.fraud_indicators.map((item, index) => <div className="finding fraud-finding" key={`fraud-${index}`}><div className="finding-top"><strong>{item.title}</strong><span className={`pill ${item.severity}`}>{item.indicator_type}</span></div><p>{item.explanation}</p><div className="citation">{item.page ? `page ${item.page}` : ""}{item.text_span ? ` · “${item.text_span}”` : ""}</div></div>) : <p className="muted">{t("report.noFraud")}</p>}</>}
    <h3>{t("report.deadlines")}</h3>
    {displayedReport.deadlines.length ? displayedReport.deadlines.map(deadline => <div className="timeline-item" key={`${deadline.title}-${deadline.date}`}><span className="timeline-dot" /><div><strong>{deadline.title}</strong><small>{formatDate(deadline.date)} · {deadline.priority} priority · {deadline.source}</small></div></div>) : <p className="muted">{t("report.noDeadlines")}</p>}
    <h3>{t("report.actionPlan")}</h3>
    {displayedReport.action_plan?.length ? displayedReport.action_plan.map(item => <label className={`action-item${item.status === "completed" ? " completed" : ""}`} key={item.id || item.title}><input type="checkbox" checked={item.status === "completed"} onChange={event => updateAction(item, event.target.checked)} /> <span><strong>{item.title}</strong><small>{item.detail} · {item.priority}{item.due_date ? ` · due ${formatDate(item.due_date)}` : ""}</small></span></label>) : <p className="muted">{t("report.noActions")}</p>}
    <h3>{t("report.recommendations")}</h3>
    {displayedReport.recommendations.length ? displayedReport.recommendations.map(item => <div className="timeline-item" key={item}><span className="timeline-dot" /><div><strong>{item}</strong><small>Evidence-backed action</small></div></div>) : <p className="muted">{t("report.noRecommendations")}</p>}
    <h3>{t("report.evidence")}</h3>
    {activeReport.evidence?.length ? activeReport.evidence.map((item, index) => <div className="citation evidence-row" key={`${item.label}-${index}`}>▣ {item.label}{item.page ? ` · page ${item.page}` : ""} · “{item.text_span}” · {Math.round(item.confidence * 100)}%</div>) : <p className="muted">{t("report.noEvidence")}</p>}
  </div>;
}

function CalendarScreen({ deadlines, onRemind, onRefresh, notifications }: { deadlines: Deadline[]; onRemind: (id: string, options: ReminderOptions) => void; onRefresh: () => void; notifications: NotificationItem[] }) {
  const [cursor, setCursor] = useState(() => { const now = new Date(); return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1)); });
  const [daysBefore, setDaysBefore] = useState(7);
  const [channel, setChannel] = useState<ReminderOptions["channel"]>("in_app");
  const year = cursor.getUTCFullYear();
  const month = cursor.getUTCMonth();
  const daysInMonth = new Date(Date.UTC(year, month + 1, 0)).getUTCDate();
  const startWeekday = new Date(Date.UTC(year, month, 1)).getUTCDay();
  const byDay = useMemo(() => {
    const map = new Map<number, Deadline[]>();
    for (const deadline of deadlines) {
      const date = new Date(deadline.due_date);
      if (Number.isNaN(date.getTime()) || date.getUTCFullYear() !== year || date.getUTCMonth() !== month) continue;
      const day = date.getUTCDate();
      map.set(day, [...(map.get(day) || []), deadline]);
    }
    return map;
  }, [deadlines, year, month]);
  const cells = [...Array(startWeekday).fill(null), ...Array.from({ length: daysInMonth }, (_, index) => index + 1)];
  return <div className="workspace-grid">
    <div className="card workspace-card">
      <div className="panel-head calendar-head"><h2>{cursor.toLocaleString("en", { month: "long", year: "numeric", timeZone: "UTC" })}</h2><div className="doc-actions"><button className="view" onClick={() => setCursor(new Date(Date.UTC(year, month - 1, 1)))}>←</button><button className="view" onClick={() => setCursor(new Date(Date.UTC(year, month + 1, 1)))}>→</button></div></div>
      <div className="calendar-weekdays">{["Sun", "Mon", "Tue", "Wed", "Thu", "Fri", "Sat"].map(day => <span key={day}>{day}</span>)}</div>
      <div className="calendar-grid">{cells.map((day, index) => <div className={`calendar-cell ${day ? "" : "empty"}`} key={`${day}-${index}`}><strong>{day || ""}</strong>{day && (byDay.get(day) || []).map(item => <button key={item.id} className={`cal-event ${item.priority}`} onClick={() => onRemind(item.id, { channel, days_before: daysBefore })} title={item.title}>{item.title}</button>)}</div>)}</div>
    </div>
    <div className="card workspace-card">
      <h2>Upcoming events</h2>
      <div className="reminder-controls"><label>Notify <select value={channel} onChange={event => setChannel(event.target.value as ReminderOptions["channel"])}><option value="in_app">In-app</option><option value="email">Email</option></select></label><label>Days before <select value={daysBefore} onChange={event => setDaysBefore(Number(event.target.value))}><option value={0}>Same day</option><option value={1}>1 day</option><option value={3}>3 days</option><option value={7}>7 days</option><option value={14}>14 days</option><option value={30}>30 days</option></select></label></div>
      {deadlines.length ? deadlines.map(item => <div className="timeline-item" key={item.id}><span className="timeline-dot" /><div><strong>{item.title}</strong><small>{item.document_name ? `${item.document_name} · ` : ""}{formatDate(item.due_date)} · {item.priority} priority · {item.source}</small></div><button className="view" onClick={() => onRemind(item.id, { channel, days_before: daysBefore })}>Schedule</button></div>) : <EmptyState title="No deadlines found" text="Upload and analyze documents to extract dates." />}
      <h2>Recent notifications</h2>
      {notifications.length ? notifications.slice(0, 5).map(item => <div className="finding" key={item.id}><strong>{item.title}</strong><p>{item.body}</p><small>{formatDate(item.created_at)} · {item.channel}</small></div>) : <p className="muted">No reminders delivered yet.</p>}
      <button className="primary" onClick={onRefresh}>Refresh deadlines</button>
    </div>
  </div>;
}

function ComparisonScreen({ docs, compareIds, setCompareIds, compare, comparison, t }: { docs: DocumentItem[]; compareIds: string[]; setCompareIds: (ids: string[]) => void; compare: () => void; comparison: Record<string, unknown> | null; t: (key: MessageKey) => string }) {
  const list = (value: unknown) => Array.isArray(value) ? value.map(String) : [];
  const modified = Array.isArray(comparison?.modified_clauses) ? comparison?.modified_clauses as Array<Record<string, string>> : [];
  const deadlineChanges = Array.isArray(comparison?.deadline_changes) ? comparison?.deadline_changes as Array<Record<string, string>> : [];
  const riskDelta = typeof comparison?.risk_score_delta === "number" ? comparison.risk_score_delta as number : null;
  const riskLevelChanged = Boolean(comparison?.risk_level_changed);
  const disclaimer = typeof comparison?.disclaimer === "string" ? comparison.disclaimer as string : "";
  return <div className="card workspace-card"><h2>{t("compare.title")}</h2>{docs.length < 2 ? <EmptyState title="Two analyzed documents required" text={t("compare.needTwo")} /> : <><div className="comparison"><select value={compareIds[0]} onChange={event => setCompareIds([event.target.value, compareIds[1]])}>{docs.map(doc => <option key={doc.id} value={doc.id}>{doc.name}</option>)}</select><select value={compareIds[1]} onChange={event => setCompareIds([compareIds[0], event.target.value])}>{docs.map(doc => <option key={doc.id} value={doc.id}>{doc.name}</option>)}</select></div><button className="primary" style={{ marginTop: 16 }} onClick={compare}>{t("compare.button")}</button>{comparison && <div className="comparison-result"><div className="comparison-metrics"><div className="metric"><strong>{String(comparison.similarity_score)}%</strong><small>{t("compare.similarity")}</small></div>{riskDelta !== null && <div className="metric"><strong>{riskDelta > 0 ? `+${riskDelta}` : riskDelta}</strong><small>{t("compare.riskDelta")}</small></div>}{riskLevelChanged && <div className="metric warning-metric"><strong>!</strong><small>{t("compare.riskLevelChanged")}</small></div>}</div><div className="comparison"><div className="comparison-col"><h3>{t("compare.addedRisks")}</h3>{list(comparison.added_risks).map(item => <p key={item}>＋ {item}</p>)}{!list(comparison.added_risks).length && <p className="muted">—</p>}<h3>{t("compare.addedDeadlines")}</h3>{list(comparison.added_deadlines).map(item => <p key={item}>＋ {item}</p>)}{!list(comparison.added_deadlines).length && <p className="muted">—</p>}<h3>{t("compare.addedClauses")}</h3>{list(comparison.added_clauses).map(item => <p key={item}>＋ {item}</p>)}{!list(comparison.added_clauses).length && <p className="muted">—</p>}</div><div className="comparison-col"><h3>{t("compare.removedRisks")}</h3>{list(comparison.removed_risks).map(item => <p key={item}>− {item}</p>)}{!list(comparison.removed_risks).length && <p className="muted">—</p>}<h3>{t("compare.removedDeadlines")}</h3>{list(comparison.removed_deadlines).map(item => <p key={item}>− {item}</p>)}{!list(comparison.removed_deadlines).length && <p className="muted">—</p>}<h3>{t("compare.removedClauses")}</h3>{list(comparison.removed_clauses).map(item => <p key={item}>− {item}</p>)}{!list(comparison.removed_clauses).length && <p className="muted">—</p>}</div></div>{!!deadlineChanges.length && <><h3>{t("compare.deadlineChanges")}</h3>{deadlineChanges.map(item => <div className="finding" key={item.title}><strong>{item.title}</strong><p>{formatDate(item.document_a_date || "")} → {formatDate(item.document_b_date || "")}</p></div>)}</>}{!!modified.length && <><h3>{t("compare.modifiedClauses")}</h3>{modified.map(item => <div className="finding" key={item.title}><strong>{item.title}</strong><p>A ({item.document_a_severity}): {item.document_a_excerpt}</p><p>B ({item.document_b_severity}): {item.document_b_excerpt}</p></div>)}</>}{disclaimer && <p className="comparison-disclaimer">{disclaimer}</p>}</div>}</>}</div>;
}

function AnalyticsScreen({ analytics, t }: { analytics: Analytics | null; t: (key: MessageKey) => string }) {
  if (!analytics) return <EmptyState title={t("page.analytics.title")} text={t("page.analytics.subtitle")} />;
  const total = Math.max(analytics.documents_uploaded, 1);
  const monthlyMax = Math.max(1, ...(analytics.monthly_uploads || []).map(item => item.count));
  return <div className="workspace-grid">
    <div className="card workspace-card"><h2>{t("stat.highRisk")}</h2><div className="chart-row"><div className="bar" style={{ height: `${Math.max(6, analytics.high_risk_documents / total * 100)}%` }}><span>{analytics.high_risk_documents}</span></div><div className="bar" style={{ height: `${Math.max(6, analytics.medium_risk_documents / total * 100)}%`, background: "linear-gradient(#f8c75e,#f59e0b)" }}><span>{analytics.medium_risk_documents}</span></div><div className="bar" style={{ height: `${Math.max(6, analytics.low_risk_documents / total * 100)}%`, background: "linear-gradient(#53d3a5,#10b981)" }}><span>{analytics.low_risk_documents}</span></div></div><div className="chart-labels"><span>{t("stat.highRisk")}</span><span>{t("stat.mediumRisk")}</span><span>{t("stat.lowRisk")}</span></div></div>
    <div className="card workspace-card"><h2>{t("page.analytics.title")}</h2><div className="stats analytics-stats"><Stat icon="▤" label={t("stat.documents")} value={String(analytics.documents_uploaded)} foot="total" /><Stat icon="!" label={t("stat.highRisk")} value={String(analytics.average_risk_score)} foot="out of 100" tone="orange" /><Stat icon="✓" label={t("stat.protection")} value={`${analytics.protection_score}%`} foot="score" tone="green" /></div></div>
    <div className="card workspace-card"><h2>Categories</h2>{analytics.categories?.length ? analytics.categories.map(item => <div className="timeline-item" key={item.category}><span className="timeline-dot" /><div><strong>{item.category}</strong><small>{item.count} documents</small></div></div>) : <p className="muted">No classifications yet.</p>}</div>
    <div className="card workspace-card"><h2>Monthly uploads</h2><div className="chart-row">{(analytics.monthly_uploads || []).map(item => <div className="bar" key={item.month} style={{ height: `${Math.max(6, item.count / monthlyMax * 100)}%` }} title={item.month}><span>{item.count}</span></div>)}</div><div className="chart-labels">{(analytics.monthly_uploads || []).map(item => <span key={item.month}>{item.month}</span>)}</div></div>
  </div>;
}

function SettingsScreen({ user, features, audit, notifications, language, languages, token, t, onLanguageChange, onToast }: { user: User; features: Features | null; audit: AuditItem[]; notifications: NotificationItem[]; language: string; languages: string[]; token: string; t: (key: MessageKey) => string; onLanguageChange: (language: string) => void; onToast: (message: string) => void }) {
  const [integrations, setIntegrations] = useState<CalendarIntegration[]>([]);
  const [calendarEnabled, setCalendarEnabled] = useState(false);

  useEffect(() => {
    if (!features?.external_calendar) return;
    apiFetch("/api/v1/integrations/calendar", token).then(async response => {
      if (!response.ok) return;
      const data = await response.json();
      setCalendarEnabled(Boolean(data.enabled));
      setIntegrations(data.integrations || []);
    }).catch(() => undefined);
  }, [features?.external_calendar, token]);

  async function connectGoogle() {
    const response = await apiFetch("/api/v1/integrations/calendar/google/authorize", token);
    if (!response.ok) { onToast(t("settings.calendarFailed")); return; }
    const data = await response.json();
    window.location.href = data.authorization_url;
  }

  async function connectOutlook() {
    const response = await apiFetch("/api/v1/integrations/calendar/outlook/authorize", token);
    if (!response.ok) { onToast(t("settings.calendarFailed")); return; }
    const data = await response.json();
    window.location.href = data.authorization_url;
  }

  async function disconnect(provider: string) {
    const response = await apiFetch(`/api/v1/integrations/calendar/${provider}`, token, { method: "DELETE" });
    if (response.ok) {
      setIntegrations(items => items.filter(item => item.provider !== provider));
      onToast(`${provider} disconnected.`);
    }
  }

  async function syncAll() {
    const response = await apiFetch("/api/v1/integrations/calendar/sync", token, { method: "POST" });
    if (!response.ok) { onToast(t("settings.calendarFailed")); return; }
    const data = await response.json();
    onToast(data.message || t("settings.calendarConnected"));
  }

  async function toggleAutoSync(integration: CalendarIntegration, enabled: boolean) {
    const response = await apiFetch(`/api/v1/integrations/calendar/${integration.id}/auto-sync`, token, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ enabled }),
    });
    if (response.ok) setIntegrations(items => items.map(item => item.id === integration.id ? { ...item, auto_sync: enabled } : item));
  }

  return <div className="workspace-grid">
    <div className="card workspace-card"><h2>{t("settings.account")}</h2><p className="report-summary"><strong>{user.name}</strong><br />{user.email}<br />{t("common.role")}: {user.role}<br />{t("common.organization")}: {user.organization_id}</p>{features?.translation && <><h3>{t("settings.language")}</h3><p className="muted">{t("settings.languageHint")}</p><LanguageSelect value={language} languages={languages} onChange={onLanguageChange} /></>}<h3>{t("settings.features")}</h3><p className="muted">Voice: {features?.voice ? t("common.on") : t("common.off")} · Translation: {features?.translation ? t("common.on") : t("common.off")} · Fraud: {features?.fraud ? t("common.on") : t("common.off")} · Demo auth: {features?.demo_auth ? t("common.on") : t("common.off")}</p>{calendarEnabled && <><h3>{t("settings.calendar")}</h3><div className="calendar-actions"><button className="view" onClick={connectGoogle}>{t("settings.connectGoogle")}</button><button className="view" onClick={connectOutlook}>{t("settings.connectOutlook")}</button><button className="primary" onClick={syncAll}>{t("settings.syncNow")}</button></div>{integrations.map(item => <div className="finding" key={item.id}><strong>{item.provider}</strong><p>{item.last_sync_at ? `Last sync: ${formatDate(item.last_sync_at)}` : "Not synced yet"}</p><label className="action-item"><input type="checkbox" checked={item.auto_sync} onChange={event => toggleAutoSync(item, event.target.checked)} /> {t("settings.autoSync")}</label><button className="view danger" onClick={() => disconnect(item.provider)}>{t("settings.disconnect")}</button></div>)}{!integrations.length && <p className="muted">Connect Google or Outlook to push extracted deadlines.</p>}</>}</div>
    <div className="card workspace-card"><h2>{t("settings.notifications")}</h2>{notifications.length ? notifications.slice(0, 8).map(item => <div className="finding" key={item.id}><strong>{item.title}</strong><p>{item.body}</p></div>) : <p className="muted">{t("settings.noNotifications")}</p>}<h2>{t("settings.audit")}</h2>{audit.length ? audit.slice(0, 12).map(item => <div className="timeline-item" key={item.id}><span className="timeline-dot" /><div><strong>{item.action}</strong><small>{formatDate(item.created_at)}{item.document_id ? ` · ${item.document_id.slice(0, 8)}` : ""}</small></div></div>) : <p className="muted">{t("settings.noAudit")}</p>}</div>
  </div>;
}

function LanguageSelect({ value, languages, onChange, disabled = false }: { value: string; languages: string[]; onChange: (language: string) => void; disabled?: boolean }) {
  return <select className="language-select" value={value} onChange={event => onChange(event.target.value)} disabled={disabled} aria-label="Language">
    {languages.map(language => <option key={language} value={language}>{language}</option>)}
  </select>;
}

function ChatMessageBubble({ message, onSuggestedPrompt, disabled }: { message: ChatMessage; onSuggestedPrompt: (text: string) => void; disabled: boolean }) {
  return <div className={`message ${message.role} message-enter`}>
    <div className={message.role === "ai" ? "chat-markdown" : "chat-plain"}>
      {message.role === "ai" ? <ChatMarkdown text={message.text} /> : message.text}
    </div>
    {!!message.citations?.length && <ChatCitations citations={message.citations} />}
    {!!message.suggestedPrompts?.length && <div className="follow-up-prompts"><span className="follow-up-label">Suggested follow-ups</span><div className="follow-up-list">{message.suggestedPrompts.map(prompt => <button className="follow-up-chip" key={prompt} type="button" onClick={() => onSuggestedPrompt(prompt)} disabled={disabled}>{prompt}</button>)}</div></div>}
  </div>;
}

function ChatCitations({ citations }: { citations: NonNullable<ChatMessage["citations"]> }) {
  return <div className="chat-sources">
    <span className="chat-sources-label">Sources</span>
    <div className="chat-sources-list">
      {citations.map((citation, index) => {
        const fullLabel = cleanCitationLabel(citation.label);
        const preview = truncateCitationLabel(fullLabel);
        return <div className="chat-citation" key={`${citation.label}-${index}`} title={fullLabel}>
          <span className="chat-citation-icon" aria-hidden="true">{index + 1}</span>
          <div className="chat-citation-body">
            <p className="chat-citation-text">{preview}</p>
            {citation.page ? <span className="chat-citation-meta">Page {citation.page}</span> : null}
          </div>
        </div>;
      })}
    </div>
  </div>;
}

function cleanCitationLabel(label: string) {
  return label
    .replace(/\s+/g, " ")
    .replace(/^Page\s+\d+\s+of\s+\d+\s*/i, "")
    .replace(/^Document\s+No\.?\s*[\d/]+\s*/i, "")
    .trim();
}

function truncateCitationLabel(label: string, maxLength = 130) {
  if (label.length <= maxLength) return label;
  const cut = label.slice(0, maxLength);
  const lastSpace = cut.lastIndexOf(" ");
  return `${(lastSpace > 70 ? cut.slice(0, lastSpace) : cut).trim()}…`;
}

function ChatMarkdown({ text }: { text: string }) {
  const blocks = text.split(/\n{2,}/).map(block => block.trim()).filter(Boolean);
  if (!blocks.length) return null;
  return <>{blocks.map((block, index) => renderMarkdownBlock(block, index))}</>;
}

function renderMarkdownBlock(block: string, index: number) {
  const lines = block.split("\n").map(line => line.trim()).filter(Boolean);
  if (!lines.length) return null;
  if (lines.every(line => /^[-*]\s+/.test(line))) {
    return <ul className="chat-list" key={index}>{lines.map(line => <li key={line}>{formatInlineMarkdown(line.replace(/^[-*]\s+/, ""))}</li>)}</ul>;
  }
  if (lines.every(line => /^\d+\.\s+/.test(line))) {
    return <ol className="chat-list" key={index}>{lines.map(line => <li key={line}>{formatInlineMarkdown(line.replace(/^\d+\.\s+/, ""))}</li>)}</ol>;
  }
  const heading = lines[0].match(/^(#{1,3})\s+(.+)$/);
  if (heading && lines.length === 1) {
    const level = heading[1].length;
    const className = level <= 2 ? "chat-heading" : "chat-subheading";
    return <p className={className} key={index}>{formatInlineMarkdown(heading[2])}</p>;
  }
  return <p className="chat-paragraph" key={index}>{formatInlineMarkdown(lines.join(" "))}</p>;
}

function formatInlineMarkdown(text: string) {
  const parts = text.split(/(\*\*[^*]+\*\*|`[^`]+`)/g).filter(part => part.length > 0);
  return parts.map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**")) return <strong key={index}>{part.slice(2, -2)}</strong>;
    if (part.startsWith("`") && part.endsWith("`")) return <code className="chat-code" key={index}>{part.slice(1, -1)}</code>;
    return <Fragment key={index}>{part}</Fragment>;
  });
}

function ChatTypingIndicator() {
  return <div className="message ai typing-indicator message-enter" aria-live="polite" aria-label="Assistant is typing">
    <div className="typing-dots"><span /><span /><span /></div>
    <span className="typing-label">Searching your document and drafting a grounded answer…</span>
  </div>;
}

function DocumentRow({ doc, compact = false }: { doc: DocumentItem; compact?: boolean }) {
  const type = doc.name.split(".").pop()?.toUpperCase() || "FILE";
  return <>
    <div className={`file-icon ${type === "PDF" ? "pdf" : ""}`}>{type}</div>
    <div className="doc-info">
      <div className="doc-title">{doc.name}</div>
      <div className="doc-meta">{doc.classification || type} · {formatDate(doc.created_at)}</div>
    </div>
    <div className={`risk ${doc.risk_level || "low"}`}>
      <span className="risk-dot" />
      {doc.status === "completed" ? `${doc.risk_level || "unknown"} · ${doc.risk_score ?? "—"}` : doc.status === "failed" ? "Failed" : `${doc.stage || "Queued"} · ${doc.progress}%`}
    </div>
    {!compact && <div className="status">{doc.status}</div>}
  </>;
}
function DeadlineRow({ deadline }: { deadline: Deadline }) {
  const date = parseDate(deadline.due_date);
  return <div className="deadline-item"><div className="date-box"><strong>{date ? String(date.getUTCDate()) : "—"}</strong>{date ? date.toLocaleString("en", { month: "short", timeZone: "UTC" }).toUpperCase() : "—"}</div><div><div className="deadline-title">{deadline.title}</div><div className="deadline-meta">{formatDate(deadline.due_date)} · {deadline.priority} priority</div></div></div>;
}
function ProcessingModal({ processing, onClose }: { processing: { name: string; progress: number; stage: string; stages: Stage[] }; onClose: () => void }) {
  return <div className="upload-modal" role="dialog" aria-modal="true"><div className="modal processing-modal"><div className="modal-head"><h2>Analyzing {processing.name}</h2><button className="close" onClick={onClose} aria-label="Close">×</button></div><div className="processing-body"><div className="drop-icon">✦</div><p>Processing is running in the document pipeline.</p><div className="score-track"><div className="score-fill" style={{ width: `${processing.progress}%` }} /></div><strong>{processing.progress}% · {processing.stage}</strong><div className="stage-list">{processing.stages.map(stage => <div key={stage.stage} className={stage.status}><span>{stage.status === "completed" ? "✓" : stage.status === "running" ? "•" : "○"}</span>{stage.stage}</div>)}</div></div></div></div>;
}
function Stat({ icon, label, value, foot, tone }: { icon: string; label: string; value: string; foot: React.ReactNode; tone?: string }) { return <div className="card stat"><div className="stat-top"><span>{label}</span><span className="stat-icon" data-tone={tone}>{icon}</span></div><div className="stat-value">{value}</div><div className="stat-foot">{foot}</div></div>; }
function EmptyState({ title, text, action, actionLabel }: { title: string; text: string; action?: () => void; actionLabel?: string }) { return <div className="empty-state"><strong>{title}</strong><p>{text}</p>{action && <button className="btn btn-secondary" onClick={action}>{actionLabel || "Try again"}</button>}</div>; }
function parseDate(value: string) {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? null : date;
}

function formatDate(value: string) {
  const date = parseDate(value);
  return date ? date.toLocaleDateString() : value || "—";
}
