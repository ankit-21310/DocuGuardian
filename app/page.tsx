"use client";

import { ChangeEvent, DragEvent, FormEvent, Fragment, useEffect, useMemo, useRef, useState } from "react";

type User = { id: string; email: string; name: string; role: string; organization_id: string };
type DocumentItem = { id: string; name: string; content_type: string; size: number; status: string; stage?: string; progress: number; risk_level?: "high" | "medium" | "low"; risk_score?: number; classification?: string; created_at: string; updated_at: string; report?: Report | null };
type Stage = { stage: string; status: string; progress: number; error?: string | null };
type Deadline = { id: string; document_id: string; title: string; due_date: string; priority: string; source: string; timezone?: string };
type Analytics = { documents_uploaded: number; high_risk_documents: number; medium_risk_documents: number; low_risk_documents: number; average_risk_score: number; protection_score: number; upcoming_deadlines: number; categories?: Array<{ category: string; count: number }>; monthly_uploads?: Array<{ month: string; count: number }> };
type Risk = { title: string; severity: string; explanation: string; recommendation: string; source: string; page?: number | null; text_span?: string | null; confidence?: number; is_penalty?: boolean };
type Clause = { title: string; body: string; severity: string; category: string; page?: number | null; text_span?: string | null; confidence?: number };
type ActionItem = { title: string; detail: string; priority: string; due_date?: string | null; status?: string };
type Report = { summary: string; classification: string; risk_score: number; risk_level: string; confidence: number; risks: Risk[]; clauses?: Clause[]; hidden_penalties?: Risk[]; deadlines: Array<{ title: string; date: string; priority: string; source: string; page?: number | null }>; recommendations: string[]; action_plan?: ActionItem[]; evidence?: Array<{ page?: number | null; text_span: string; label: string; confidence: number }>; model_version?: string };
type ChatMessage = {
  role: "ai" | "user";
  text: string;
  citations?: Array<{ label: string; page?: number; confidence?: number }>;
  suggestedPrompts?: string[];
};
type Session = { token: string; user: User };
type Features = { voice: boolean; translation: boolean; demo_auth: boolean; pipeline_stages: string[]; supported_languages?: string[] };
type NotificationItem = { id: string; title: string; body: string; channel: string; status: string; created_at: string };
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
const nav = [["◈", "Dashboard"], ["▤", "Documents"], ["✦", "AI Chat"], ["□", "Calendar"], ["◫", "Compare"], ["◒", "Analytics"], ["⚙", "Settings"]];

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
  const [active, setActive] = useState("Dashboard");
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

  useEffect(() => { setLanguage(readLanguage()); }, []);

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

  if (session === undefined) return <div className="loading-screen">Loading workspace…</div>;
  if (!session) {
    if (authView === "landing") return <LandingPage onSignIn={() => setAuthView("auth")} onWatchDemo={() => setAuthView("auth")} features={features} />;
    return <AuthScreen features={features} onBack={() => setAuthView("landing")} onAuthenticated={next => setSession(next)} />;
  }

  const currentPage = active === "Dashboard"
    ? <Dashboard docs={docs} deadlines={deadlines} analytics={analytics} loading={loading} onUpload={() => setUploadOpen(true)} onOpenDocuments={() => setActive("Documents")} onOpenChat={() => setActive("AI Chat")} onOpenCalendar={() => setActive("Calendar")} />
    : <WorkspaceScreen active={active} docs={docs} deadlines={deadlines} analytics={analytics} notifications={notifications} features={features} user={session.user} token={session.token} language={language} onLanguageChange={next => { writeLanguage(next); setLanguage(next); setToast(`Language set to ${next}.`); }} onUpload={() => setUploadOpen(true)} onRefresh={() => loadWorkspace(session)} onToast={setToast} />;

  return <div className="app-shell">
    <aside className="sidebar"><div className="brand"><span className="brand-mark">D</span><span>DocuGuardian</span></div><div className="nav-label">Workspace</div><nav className="nav">{nav.map(([icon, label]) => <button key={label} className={active === label ? "active" : ""} onClick={() => setActive(label)}><span className="nav-icon">{icon}</span><span>{label}</span></button>)}</nav><div className="sidebar-bottom"><div className="user"><span className="avatar">{initials(session.user.name)}</span><div><b>{session.user.name}</b><small>{session.user.role} · {session.user.email}</small></div></div><button className="signout" onClick={signOut}>Sign out</button></div></aside>
    <main className="main"><header className="topbar"><div className="crumb">Workspace / <strong>{active}</strong></div><div className="top-actions">{notifications.length > 0 && <span className="bell" title={`${notifications.length} notifications`}>🔔</span>}<span className="avatar">{initials(session.user.name)}</span></div></header><section className="content">{currentPage}</section></main>
    {uploadOpen && <div className="upload-modal" role="dialog" aria-modal="true"><div className="modal"><div className="modal-head"><h2>Upload a document</h2><button className="close" onClick={() => setUploadOpen(false)} aria-label="Close">×</button></div><div className="drop" onDragOver={event => event.preventDefault()} onDrop={onDrop}><div className="drop-icon">↑</div><strong>Drop your document here</strong><p>We’ll analyze risks, deadlines, clauses, and recommendations.</p><label className="browse">Browse files<input type="file" accept=".pdf,.docx,.png,.jpg,.jpeg" onChange={onFileChange} /></label></div><div className="format">Supported: PDF, DOCX, JPG, PNG · Max file size 25 MB</div>{uploadError && <p className="form-error">{uploadError}</p>}</div></div>}
    {processing && processingVisible && <ProcessingModal processing={processing} onClose={() => setProcessingVisible(false)} />}
    {toast && <div className="toast">{toast}</div>}
  </div>;
}

function initials(name: string) { return name.split(/\s+/).map(part => part[0]).join("").slice(0, 2).toUpperCase(); }

function LandingPage({ onSignIn, onWatchDemo, features }: { onSignIn: () => void; onWatchDemo: () => void; features: Features | null }) {
  return <div className="landing">
    <div className="landing-hero">
      <div className="landing-brand"><span className="brand-mark">D</span><span>DocuGuardian</span></div>
      <h1>Protect Every Document Before It Costs You</h1>
      <p>Transform contracts, policies, and reports into risk scores, deadlines, and clear next actions—before you sign.</p>
      <div className="landing-cta"><button className="primary" onClick={onSignIn}>Get started</button><button className="ghost" onClick={onWatchDemo}>Watch demo</button></div>
    </div>
    <div className="landing-grid">
      {["Plain-language summary", "Risk score 0–100", "Hidden penalty detection", "Deadline reminders", "Grounded AI chat", "Multi-language translation", "Voice summary", "Contract comparison"].map(item => <div className="landing-feature" key={item}><strong>{item}</strong><p>Evidence-backed intelligence from your uploaded documents.</p></div>)}
    </div>
    {features?.pipeline_stages?.length ? <p className="landing-note">Live pipeline: {features.pipeline_stages.join(" → ")}</p> : null}
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

function Dashboard({ docs, deadlines, analytics, loading, onUpload, onOpenDocuments, onOpenChat, onOpenCalendar }: { docs: DocumentItem[]; deadlines: Deadline[]; analytics: Analytics | null; loading: boolean; onUpload: () => void; onOpenDocuments: () => void; onOpenChat: () => void; onOpenCalendar: () => void }) {
  const protection = analytics?.protection_score ?? (analytics ? Math.max(0, 100 - analytics.average_risk_score) : 0);
  return <><div className="intro"><div><h1>{greetingForNow()}</h1><p>Here’s what’s happening with your documents.</p></div><button className="primary" onClick={onUpload}>＋ Upload document</button></div><div className="stats"><Stat icon="▤" label="Documents uploaded" value={analytics ? String(analytics.documents_uploaded) : "—"} foot="Persisted in workspace" /><Stat icon="!" label="High risk documents" value={analytics ? String(analytics.high_risk_documents) : "—"} foot="Needs your attention" tone="red" /><Stat icon="◷" label="Upcoming deadlines" value={analytics ? String(analytics.upcoming_deadlines) : "—"} foot="Extracted from documents" tone="orange" /><Stat icon="✓" label="Protection score" value={analytics ? `${protection}%` : "—"} foot="From workspace analytics" tone="green" /></div>{loading ? <EmptyState title="Loading workspace" text="Fetching your documents and deadlines…" /> : <div className="grid"><div className="card docs"><div className="panel-head"><h2>Recent documents</h2><button className="view" onClick={onOpenDocuments}>View all →</button></div>{docs.length ? docs.slice(0, 6).map(doc => <div className="doc-row" key={doc.id}><DocumentRow doc={doc} /></div>) : <EmptyState title="No documents yet" text="Upload a document to start your first analysis." action={onUpload} actionLabel="Upload document" />}</div><div><div className="card deadline"><div className="panel-head"><h2>Upcoming deadlines</h2><button className="view" onClick={onOpenCalendar}>Calendar →</button></div>{deadlines.length ? deadlines.slice(0, 5).map(deadline => <DeadlineRow key={deadline.id} deadline={deadline} />) : <EmptyState title="No deadlines found" text="Deadlines will appear here when they are extracted from a report." />}</div><div className="insight"><h3>✦ Evidence-backed workspace</h3><p>Open an analyzed report to review source evidence, confidence, deadlines, and recommendations.</p><button onClick={onOpenChat}>Ask DocuGuardian →</button></div></div></div>}</>;
}

function WorkspaceScreen({ active, docs, deadlines, analytics, notifications, features, user, token, language, onLanguageChange, onUpload, onRefresh, onToast }: { active: string; docs: DocumentItem[]; deadlines: Deadline[]; analytics: Analytics | null; notifications: NotificationItem[]; features: Features | null; user: User; token: string; language: string; onLanguageChange: (language: string) => void; onUpload: () => void; onRefresh: () => void; onToast: (message: string) => void }) {
  const [report, setReport] = useState<Report | null>(null);
  const [reportDoc, setReportDoc] = useState<DocumentItem | null>(null);
  const [question, setQuestion] = useState("");
  const [selectedChatDoc, setSelectedChatDoc] = useState("");
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [chatLoading, setChatLoading] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const [compareIds, setCompareIds] = useState(["", ""]);
  const [comparison, setComparison] = useState<Record<string, unknown> | null>(null);
  const [error, setError] = useState("");
  const [audit, setAudit] = useState<AuditItem[]>([]);
  const analyzedDocs = docs.filter(doc => doc.status === "completed");
  const prompts = useMemo(() => {
    const names = analyzedDocs.slice(0, 1).map(doc => doc.name);
    const base = names[0] ? [`Summarize risks in ${names[0]}`, `What deadlines matter in ${names[0]}?`] : ["Summarize the key risks", "What deadlines should I track?"];
    return [...base, "Explain this like I’m 15", "What should I negotiate next?"];
  }, [analyzedDocs]);

  useEffect(() => {
    if (!selectedChatDoc && analyzedDocs[0]) setSelectedChatDoc(analyzedDocs[0].id);
    if (!compareIds[0] && analyzedDocs[0]) setCompareIds([analyzedDocs[0].id, analyzedDocs[1]?.id || analyzedDocs[0].id]);
  }, [analyzedDocs, selectedChatDoc, compareIds]);

  useEffect(() => {
    setMessages([{ role: "ai", text: selectedChatDoc ? "Ask a question about this analyzed document and I’ll cite retrieved evidence." : "Select an analyzed document to start a grounded conversation." }]);
    setChatLoading(false);
  }, [selectedChatDoc]);

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: "smooth", block: "end" });
  }, [messages, chatLoading]);

  useEffect(() => {
    if (active !== "Settings") return;
    apiFetch("/api/v1/audit", token).then(async response => { if (response.ok) setAudit(await response.json()); }).catch(() => undefined);
  }, [active, token]);

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
      const response = await apiFetch(`/api/v1/documents/${selectedChatDoc}/chat`, token, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: text, target_language: features?.translation ? language : undefined }) });
      if (!response.ok) {
        const payload = await response.json().catch(() => null);
        const detail = payload?.detail;
        setError(typeof detail === "string" ? detail : "Chat is unavailable for this document.");
        return;
      }
      const answer = await response.json();
      setMessages(items => [...items, {
        role: "ai",
        text: answer.answer,
        citations: answer.citations,
        suggestedPrompts: answer.suggested_prompts,
      }]);
    } catch {
      setError("Unable to reach the API. Restart the backend and try again.");
    } finally {
      setChatLoading(false);
    }
  }

  async function compare() {
    if (!compareIds[0] || !compareIds[1]) return;
    const response = await apiFetch("/api/v1/comparisons", token, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ document_a_id: compareIds[0], document_b_id: compareIds[1] }) });
    if (response.ok) setComparison(await response.json());
  }

  async function remind(id: string) {
    const response = await apiFetch(`/api/v1/deadlines/${id}/reminders`, token, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ channel: "in_app", days_before: 7 }) });
    if (response.ok) { onToast("Reminder delivered to your in-app notifications."); onRefresh(); }
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

  const titles: Record<string, [string, string]> = {
    Documents: ["Document library", "Review every file, finding, and obligation in one place."],
    "AI Chat": ["Ask your documents", "Grounded answers with source citations, not guesses."],
    Calendar: ["Deadline calendar", "Stay ahead of renewals, payments, and notice periods."],
    Compare: ["Document comparison", "Compare evidence-backed reports without fabricated differences."],
    Analytics: ["Workspace analytics", "A clear view of persisted document risk and deadlines."],
    Settings: ["Workspace settings", "Account, notifications, and organization context."],
  };
  const [title, subtitle] = titles[active] || titles.Documents;

  return <>
    <div className="workspace-head"><div><h1>{title}</h1><p>{subtitle}</p></div>{active === "Documents" && <button className="primary" onClick={onUpload}>＋ Upload document</button>}</div>
    {error && <p className="form-error">{error}</p>}
    {active === "Documents" && <div className="workspace-grid"><div className="card workspace-card"><h2>All documents <span className="muted-count">({docs.length})</span></h2>{docs.length ? docs.map(doc => <div className="doc-row" key={doc.id}><DocumentRow doc={doc} compact /><div className="doc-actions"><button className="view" onClick={() => openReport(doc)} disabled={doc.status !== "completed"}>Report →</button>{(doc.status === "failed" || doc.status === "completed") && <button className="view" onClick={() => retryDoc(doc.id)}>Retry</button>}<button className="view danger" onClick={() => removeDoc(doc.id)}>Delete</button></div></div>) : <EmptyState title="No documents yet" text="Upload a document to begin." action={onUpload} actionLabel="Upload document" />}</div><ReportPanel report={report} reportDoc={reportDoc} token={token} features={features} language={language} languages={languageOptions(features)} onToast={onToast} /></div>}
    {active === "AI Chat" && <div className="chat-shell"><div className="card chat-box"><div className="chat-toolbar"><label>Document<select value={selectedChatDoc} onChange={event => setSelectedChatDoc(event.target.value)} disabled={chatLoading}><option value="">Select an analyzed document</option>{analyzedDocs.map(doc => <option key={doc.id} value={doc.id}>{doc.name}</option>)}</select></label>{features?.translation && <label>Response language<LanguageSelect value={language} languages={languageOptions(features)} onChange={onLanguageChange} disabled={chatLoading} /></label>}</div><div className="messages">{messages.map((message, index) => <ChatMessageBubble key={index} message={message} onSuggestedPrompt={ask} disabled={chatLoading || !selectedChatDoc} />)} {chatLoading && <ChatTypingIndicator />}<div ref={messagesEndRef} /></div><div className="chat-input"><input value={question} onChange={event => setQuestion(event.target.value)} onKeyDown={event => event.key === "Enter" && !chatLoading && ask()} placeholder={chatLoading ? "Waiting for response…" : "Ask about your documents…"} disabled={chatLoading || !selectedChatDoc} /><button className={`primary ${chatLoading ? "loading" : ""}`} onClick={() => ask()} disabled={chatLoading || !selectedChatDoc || !question.trim()}>{chatLoading ? "Thinking…" : "Send"}</button></div></div><div className="card workspace-card"><h2>Suggested prompts</h2>{prompts.map(prompt => <button className="prompt" key={prompt} onClick={() => ask(prompt)} disabled={chatLoading || !selectedChatDoc}>{prompt} <span>→</span></button>)}<p className="disclaimer">Decision support only. Confirm important decisions with a qualified professional.</p></div></div>}
    {active === "Calendar" && <CalendarScreen deadlines={deadlines} onRemind={remind} onRefresh={onRefresh} notifications={notifications} />}
    {active === "Compare" && <ComparisonScreen docs={analyzedDocs} compareIds={compareIds} setCompareIds={setCompareIds} compare={compare} comparison={comparison} />}
    {active === "Analytics" && <AnalyticsScreen analytics={analytics} />}
    {active === "Settings" && <SettingsScreen user={user} features={features} audit={audit} notifications={notifications} language={language} languages={languageOptions(features)} onLanguageChange={onLanguageChange} />}
  </>;
}

function ReportPanel({ report, reportDoc, token, features, language, languages, onToast }: { report: Report | null; reportDoc: DocumentItem | null; token: string; features: Features | null; language: string; languages: string[]; onToast: (message: string) => void }) {
  const [translation, setTranslation] = useState("");
  const [translating, setTranslating] = useState(false);
  if (!report || !reportDoc) return <div className="card workspace-card"><h2>Intelligence report</h2><p className="report-summary">Select an analyzed document to review its summary, risks, clauses, deadlines, action plan, and source evidence.</p></div>;
  const activeReport = report;
  const activeDoc = reportDoc;

  async function download() {
    const response = await apiFetch(`/api/v1/documents/${activeDoc.id}/report/download`, token);
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const link = document.createElement("a");
    link.href = url; link.download = `${activeDoc.name}-report.json`; link.click(); URL.revokeObjectURL(url);
  }

  async function translateReport() {
    if (!features?.translation) return;
    setTranslating(true);
    try {
      const sections = [
        `Summary:\n${activeReport.summary}`,
        activeReport.recommendations.length ? `Recommendations:\n${activeReport.recommendations.map(item => `- ${item}`).join("\n")}` : "",
        activeReport.action_plan?.length ? `Action plan:\n${activeReport.action_plan.map(item => `- ${item.title}: ${item.detail}`).join("\n")}` : "",
      ].filter(Boolean).join("\n\n");
      const response = await apiFetch("/api/v1/translate", token, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: sections, target_language: language }) });
      if (!response.ok) { onToast("Translation is unavailable."); return; }
      const data = await response.json(); setTranslation(data.translated_text); onToast(`Report translated to ${language}.`);
    } finally {
      setTranslating(false);
    }
  }

  async function playVoice() {
    const response = await apiFetch("/api/v1/voice-summary", token, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ text: translation || activeReport.summary }) });
    if (!response.ok) { onToast("Voice summary is unavailable."); return; }
    const blob = await response.blob();
    const url = URL.createObjectURL(blob);
    const audio = new Audio(url);
    audio.play();
    onToast("Playing voice summary.");
  }

  return <div className="card workspace-card report-panel">
    <div className="report-header"><h2>{activeDoc.name}</h2><div className="doc-actions"><button className="view" onClick={download}>Download report</button>{features?.translation && <button className="view" onClick={translateReport} disabled={translating}>{translating ? "Translating…" : `Translate to ${language}`}</button>}{features?.voice && <button className="view" onClick={playVoice}>Voice summary</button>}</div></div>
    <div className="metric"><strong>{activeReport.risk_score}</strong><small>{activeReport.risk_level} risk · {activeReport.classification} · confidence {Math.round(activeReport.confidence * 100)}%</small></div>
    {features?.translation && <div className="language-note">Translations use your workspace language from Settings or AI Chat: <strong>{language}</strong></div>}
    <p className="report-summary">{activeReport.summary}</p>
    {translation && <div className="translation-panel"><h3>Translated report ({language})</h3><p className="report-summary">{translation}</p></div>}
    <h3>Risk analysis</h3>
    {activeReport.risks.length ? activeReport.risks.map((risk, index) => <div className="finding" key={`${risk.title}-${index}`}><div className="finding-top"><strong>{risk.title}{risk.is_penalty ? " · penalty" : ""}</strong><span className={`pill ${risk.severity}`}>{risk.severity}</span></div><p>{risk.explanation}</p><small>{risk.recommendation}</small><div className="citation">{risk.source}{risk.page ? ` · page ${risk.page}` : ""}{risk.text_span ? ` · “${risk.text_span}”` : ""}{risk.confidence ? ` · ${Math.round(risk.confidence * 100)}% confidence` : ""}</div></div>) : <p className="muted">No risks were extracted.</p>}
    {!!activeReport.hidden_penalties?.length && <><h3>Hidden penalties</h3>{activeReport.hidden_penalties.map((risk, index) => <div className="finding" key={`penalty-${index}`}><div className="finding-top"><strong>{risk.title}</strong><span className={`pill ${risk.severity}`}>{risk.severity}</span></div><p>{risk.explanation}</p></div>)}</>}
    {!!activeReport.clauses?.length && <><h3>Clauses</h3>{activeReport.clauses.map((clause, index) => <div className="finding" key={`clause-${index}`}><div className="finding-top"><strong>{clause.title}</strong><span className={`pill ${clause.severity}`}>{clause.severity}</span></div><p>{clause.body}</p><div className="citation">{clause.category}{clause.page ? ` · page ${clause.page}` : ""}{clause.text_span ? ` · “${clause.text_span}”` : ""}</div></div>)}</>}
    <h3>Deadlines</h3>
    {activeReport.deadlines.length ? activeReport.deadlines.map(deadline => <div className="timeline-item" key={`${deadline.title}-${deadline.date}`}><span className="timeline-dot" /><div><strong>{deadline.title}</strong><small>{formatDate(deadline.date)} · {deadline.priority} priority · {deadline.source}</small></div></div>) : <p className="muted">No deadlines were extracted.</p>}
    <h3>Action plan</h3>
    {activeReport.action_plan?.length ? activeReport.action_plan.map(item => <label className="action-item" key={item.title}><input type="checkbox" /> <span><strong>{item.title}</strong><small>{item.detail} · {item.priority}{item.due_date ? ` · due ${formatDate(item.due_date)}` : ""}</small></span></label>) : <p className="muted">No action plan items were extracted.</p>}
    <h3>Recommendations</h3>
    {activeReport.recommendations.length ? activeReport.recommendations.map(item => <div className="timeline-item" key={item}><span className="timeline-dot" /><div><strong>{item}</strong><small>Evidence-backed action</small></div></div>) : <p className="muted">No recommendations were extracted.</p>}
    <h3>Evidence</h3>
    {activeReport.evidence?.length ? activeReport.evidence.map((item, index) => <div className="citation evidence-row" key={`${item.label}-${index}`}>▣ {item.label}{item.page ? ` · page ${item.page}` : ""} · “{item.text_span}” · {Math.round(item.confidence * 100)}%</div>) : <p className="muted">No evidence spans were returned.</p>}
  </div>;
}

function CalendarScreen({ deadlines, onRemind, onRefresh, notifications }: { deadlines: Deadline[]; onRemind: (id: string) => void; onRefresh: () => void; notifications: NotificationItem[] }) {
  const [cursor, setCursor] = useState(() => { const now = new Date(); return new Date(Date.UTC(now.getUTCFullYear(), now.getUTCMonth(), 1)); });
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
      <div className="calendar-grid">{cells.map((day, index) => <div className={`calendar-cell ${day ? "" : "empty"}`} key={`${day}-${index}`}><strong>{day || ""}</strong>{day && (byDay.get(day) || []).map(item => <button key={item.id} className={`cal-event ${item.priority}`} onClick={() => onRemind(item.id)} title={item.title}>{item.title}</button>)}</div>)}</div>
    </div>
    <div className="card workspace-card">
      <h2>Upcoming events</h2>
      {deadlines.length ? deadlines.map(item => <div className="timeline-item" key={item.id}><span className="timeline-dot" /><div><strong>{item.title}</strong><small>{formatDate(item.due_date)} · {item.priority} priority · {item.source}</small></div><button className="view" onClick={() => onRemind(item.id)}>Remind me</button></div>) : <EmptyState title="No deadlines found" text="Upload and analyze documents to extract dates." />}
      <h2>Recent notifications</h2>
      {notifications.length ? notifications.slice(0, 5).map(item => <div className="finding" key={item.id}><strong>{item.title}</strong><p>{item.body}</p><small>{formatDate(item.created_at)} · {item.channel}</small></div>) : <p className="muted">No reminders delivered yet.</p>}
      <button className="primary" onClick={onRefresh}>Refresh deadlines</button>
    </div>
  </div>;
}

function ComparisonScreen({ docs, compareIds, setCompareIds, compare, comparison }: { docs: DocumentItem[]; compareIds: string[]; setCompareIds: (ids: string[]) => void; compare: () => void; comparison: Record<string, unknown> | null }) {
  const list = (value: unknown) => Array.isArray(value) ? value.map(String) : [];
  const modified = Array.isArray(comparison?.modified_clauses) ? comparison?.modified_clauses as Array<Record<string, string>> : [];
  return <div className="card workspace-card"><h2>Select two analyzed documents</h2>{docs.length < 2 ? <EmptyState title="Two analyzed documents required" text="Upload and complete analysis for another document before comparing." /> : <><div className="comparison"><select value={compareIds[0]} onChange={event => setCompareIds([event.target.value, compareIds[1]])}>{docs.map(doc => <option key={doc.id} value={doc.id}>{doc.name}</option>)}</select><select value={compareIds[1]} onChange={event => setCompareIds([compareIds[0], event.target.value])}>{docs.map(doc => <option key={doc.id} value={doc.id}>{doc.name}</option>)}</select></div><button className="primary" style={{ marginTop: 16 }} onClick={compare}>Compare documents</button>{comparison && <div className="comparison-result"><div className="metric"><strong>{String(comparison.similarity_score)}%</strong><small>report similarity</small></div><div className="comparison"><div className="comparison-col"><h3>Added risks</h3>{list(comparison.added_risks).map(item => <p key={item}>＋ {item}</p>)}<h3>Added deadlines</h3>{list(comparison.added_deadlines).map(item => <p key={item}>＋ {item}</p>)}<h3>Added clauses</h3>{list(comparison.added_clauses).map(item => <p key={item}>＋ {item}</p>)}</div><div className="comparison-col"><h3>Removed risks</h3>{list(comparison.removed_risks).map(item => <p key={item}>− {item}</p>)}<h3>Removed deadlines</h3>{list(comparison.removed_deadlines).map(item => <p key={item}>− {item}</p>)}<h3>Removed clauses</h3>{list(comparison.removed_clauses).map(item => <p key={item}>− {item}</p>)}</div></div>{!!modified.length && <><h3>Modified clauses</h3>{modified.map(item => <div className="finding" key={item.title}><strong>{item.title}</strong><p>A ({item.document_a_severity}): {item.document_a_excerpt}</p><p>B ({item.document_b_severity}): {item.document_b_excerpt}</p></div>)}</>}</div>}</>}</div>;
}

function AnalyticsScreen({ analytics }: { analytics: Analytics | null }) {
  if (!analytics) return <EmptyState title="Analytics unavailable" text="Analytics will appear after the workspace loads." />;
  const total = Math.max(analytics.documents_uploaded, 1);
  const monthlyMax = Math.max(1, ...(analytics.monthly_uploads || []).map(item => item.count));
  return <div className="workspace-grid">
    <div className="card workspace-card"><h2>Risk distribution</h2><div className="chart-row"><div className="bar" style={{ height: `${Math.max(6, analytics.high_risk_documents / total * 100)}%` }}><span>{analytics.high_risk_documents}</span></div><div className="bar" style={{ height: `${Math.max(6, analytics.medium_risk_documents / total * 100)}%`, background: "linear-gradient(#f8c75e,#f59e0b)" }}><span>{analytics.medium_risk_documents}</span></div><div className="bar" style={{ height: `${Math.max(6, analytics.low_risk_documents / total * 100)}%`, background: "linear-gradient(#53d3a5,#10b981)" }}><span>{analytics.low_risk_documents}</span></div></div><div className="chart-labels"><span>High risk</span><span>Medium</span><span>Low risk</span></div></div>
    <div className="card workspace-card"><h2>Workspace health</h2><div className="stats analytics-stats"><Stat icon="▤" label="Documents" value={String(analytics.documents_uploaded)} foot="total" /><Stat icon="!" label="Avg. risk" value={String(analytics.average_risk_score)} foot="out of 100" tone="orange" /><Stat icon="✓" label="Protection" value={`${analytics.protection_score}%`} foot="score" tone="green" /></div></div>
    <div className="card workspace-card"><h2>Categories</h2>{analytics.categories?.length ? analytics.categories.map(item => <div className="timeline-item" key={item.category}><span className="timeline-dot" /><div><strong>{item.category}</strong><small>{item.count} documents</small></div></div>) : <p className="muted">No classifications yet.</p>}</div>
    <div className="card workspace-card"><h2>Monthly uploads</h2><div className="chart-row">{(analytics.monthly_uploads || []).map(item => <div className="bar" key={item.month} style={{ height: `${Math.max(6, item.count / monthlyMax * 100)}%` }} title={item.month}><span>{item.count}</span></div>)}</div><div className="chart-labels">{(analytics.monthly_uploads || []).map(item => <span key={item.month}>{item.month}</span>)}</div></div>
  </div>;
}

function SettingsScreen({ user, features, audit, notifications, language, languages, onLanguageChange }: { user: User; features: Features | null; audit: AuditItem[]; notifications: NotificationItem[]; language: string; languages: string[]; onLanguageChange: (language: string) => void }) {
  return <div className="workspace-grid">
    <div className="card workspace-card"><h2>Account</h2><p className="report-summary"><strong>{user.name}</strong><br />{user.email}<br />Role: {user.role}<br />Organization: {user.organization_id}</p>{features?.translation && <><h3>Preferred language</h3><p className="muted">Used for AI Chat responses and document report translations.</p><LanguageSelect value={language} languages={languages} onChange={onLanguageChange} /></>}<h3>Feature flags</h3><p className="muted">Voice: {features?.voice ? "on" : "off"} · Translation: {features?.translation ? "on" : "off"} · Demo auth: {features?.demo_auth ? "on" : "off"}</p></div>
    <div className="card workspace-card"><h2>Notifications</h2>{notifications.length ? notifications.slice(0, 8).map(item => <div className="finding" key={item.id}><strong>{item.title}</strong><p>{item.body}</p></div>) : <p className="muted">No notifications yet.</p>}<h2>Audit log</h2>{audit.length ? audit.slice(0, 12).map(item => <div className="timeline-item" key={item.id}><span className="timeline-dot" /><div><strong>{item.action}</strong><small>{formatDate(item.created_at)}{item.document_id ? ` · ${item.document_id.slice(0, 8)}` : ""}</small></div></div>) : <p className="muted">Audit events appear for owners and admins.</p>}</div>
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
function DeadlineRow({ deadline }: { deadline: Deadline }) { return <div className="deadline-item"><div className="date-box"><strong>{new Date(deadline.due_date).getUTCDate()}</strong>{new Date(deadline.due_date).toLocaleString("en", { month: "short", timeZone: "UTC" }).toUpperCase()}</div><div><div className="deadline-title">{deadline.title}</div><div className="deadline-meta">{formatDate(deadline.due_date)} · {deadline.priority} priority</div></div></div>; }
function ProcessingModal({ processing, onClose }: { processing: { name: string; progress: number; stage: string; stages: Stage[] }; onClose: () => void }) {
  return <div className="upload-modal" role="dialog" aria-modal="true"><div className="modal processing-modal"><div className="modal-head"><h2>Analyzing {processing.name}</h2><button className="close" onClick={onClose} aria-label="Close">×</button></div><div className="processing-body"><div className="drop-icon">✦</div><p>Processing is running in the document pipeline.</p><div className="score-track"><div className="score-fill" style={{ width: `${processing.progress}%` }} /></div><strong>{processing.progress}% · {processing.stage}</strong><div className="stage-list">{processing.stages.map(stage => <div key={stage.stage} className={stage.status}><span>{stage.status === "completed" ? "✓" : stage.status === "running" ? "•" : "○"}</span>{stage.stage}</div>)}</div></div></div></div>;
}
function Stat({ icon, label, value, foot, tone }: { icon: string; label: string; value: string; foot: React.ReactNode; tone?: string }) { return <div className="card stat"><div className="stat-top"><span>{label}</span><span className="stat-icon" data-tone={tone}>{icon}</span></div><div className="stat-value">{value}</div><div className="stat-foot">{foot}</div></div>; }
function EmptyState({ title, text, action, actionLabel }: { title: string; text: string; action?: () => void; actionLabel?: string }) { return <div className="empty-state"><strong>{title}</strong><p>{text}</p>{action && <button className="view" onClick={action}>{actionLabel || "Try again"}</button>}</div>; }
function formatDate(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString(); }
