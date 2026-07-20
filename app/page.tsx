"use client";

import { ChangeEvent, DragEvent, FormEvent, useEffect, useMemo, useState } from "react";

type User = { id: string; email: string; name: string; role: string; organization_id: string };
type DocumentItem = { id: string; name: string; content_type: string; size: number; status: string; stage?: string; progress: number; risk_level?: "high" | "medium" | "low"; risk_score?: number; classification?: string; created_at: string; updated_at: string; report?: Report | null };
type Stage = { stage: string; status: string; progress: number; error?: string | null };
type Deadline = { id: string; document_id: string; title: string; due_date: string; priority: string; source: string; timezone?: string };
type Analytics = { documents_uploaded: number; high_risk_documents: number; medium_risk_documents: number; low_risk_documents: number; average_risk_score: number; upcoming_deadlines: number };
type Risk = { title: string; severity: string; explanation: string; recommendation: string; source: string; page?: number | null; text_span?: string | null; confidence?: number };
type Report = { summary: string; classification: string; risk_score: number; risk_level: string; confidence: number; risks: Risk[]; deadlines: Array<{ title: string; date: string; priority: string; source: string; page?: number | null }>; recommendations: string[]; evidence?: Array<{ page?: number | null; text_span: string; label: string; confidence: number }>; model_version?: string };
type Session = { token: string; user: User };

const API_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const nav = [["◈", "Dashboard"], ["▤", "Documents"], ["✦", "AI Chat"], ["□", "Calendar"], ["◫", "Compare"], ["◒", "Analytics"], ["⚙", "Settings"]];
const prompts = ["Show hidden risks", "Find my next deadlines", "Explain this like I’m 15", "What should I negotiate?"];

function readToken() { return typeof window === "undefined" ? "" : window.localStorage.getItem("docuguardian_token") || ""; }

async function apiFetch(path: string, token: string, init: RequestInit = {}) {
  const headers = new Headers(init.headers);
  if (token) headers.set("Authorization", `Bearer ${token}`);
  return fetch(`${API_URL}${path}`, { ...init, headers });
}

export default function Home() {
  const [session, setSession] = useState<Session | null | undefined>(undefined);
  const [active, setActive] = useState("Dashboard");
  const [docs, setDocs] = useState<DocumentItem[]>([]);
  const [deadlines, setDeadlines] = useState<Deadline[]>([]);
  const [analytics, setAnalytics] = useState<Analytics | null>(null);
  const [uploadOpen, setUploadOpen] = useState(false);
  const [uploadError, setUploadError] = useState("");
  const [processing, setProcessing] = useState<{ name: string; progress: number; stage: string; stages: Stage[] } | null>(null);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
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
      const [documentsResponse, deadlinesResponse, analyticsResponse] = await Promise.all([
        apiFetch("/api/v1/documents", current.token),
        apiFetch("/api/v1/deadlines", current.token),
        apiFetch("/api/v1/analytics/overview", current.token),
      ]);
      if ([documentsResponse, deadlinesResponse, analyticsResponse].some(response => response.status === 401)) { signOut(); return; }
      if (documentsResponse.ok) setDocs(await documentsResponse.json());
      if (deadlinesResponse.ok) setDeadlines(await deadlinesResponse.json());
      if (analyticsResponse.ok) setAnalytics(await analyticsResponse.json());
    } finally { setLoading(false); }
  }

  useEffect(() => { if (session) loadWorkspace(session); }, [session]);

  function signOut() {
    window.localStorage.removeItem("docuguardian_token");
    setSession(null); setDocs([]); setDeadlines([]); setAnalytics(null);
  }

  async function handleUpload(file?: File) {
    if (!file || !session) return;
    setUploadError("");
    const allowed = ["application/pdf", "application/vnd.openxmlformats-officedocument.wordprocessingml.document", "image/png", "image/jpeg"];
    if (!allowed.includes(file.type) && !/\.(pdf|docx|png|jpe?g)$/i.test(file.name)) { setUploadError("Use a PDF, DOCX, PNG, or JPG file."); return; }
    if (file.size > 25 * 1024 * 1024) { setUploadError("Files must be 25 MB or smaller."); return; }
    setUploadOpen(false); setProcessing({ name: file.name, progress: 0, stage: "Uploading", stages: [] });
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
    } catch (error) { setUploadError(error instanceof Error ? error.message : "Upload failed"); }
    finally { setProcessing(null); }
  }

  function onFileChange(event: ChangeEvent<HTMLInputElement>) { handleUpload(event.target.files?.[0]); event.target.value = ""; }
  function onDrop(event: DragEvent<HTMLDivElement>) { event.preventDefault(); handleUpload(event.dataTransfer.files?.[0]); }

  if (session === undefined) return <div className="loading-screen">Loading workspace…</div>;
  if (!session) return <AuthScreen onAuthenticated={next => setSession(next)} />;

  const currentPage = active === "Dashboard" ? <Dashboard docs={docs} deadlines={deadlines} analytics={analytics} loading={loading} onUpload={() => setUploadOpen(true)} onOpenDocuments={() => setActive("Documents")} onOpenChat={() => setActive("AI Chat")} /> : <WorkspaceScreen active={active} docs={docs} deadlines={deadlines} analytics={analytics} apiUrl={API_URL} token={session.token} onUpload={() => setUploadOpen(true)} onRefresh={() => loadWorkspace(session)} />;
  return <div className="app-shell">
    <aside className="sidebar"><div className="brand"><span className="brand-mark">D</span><span>DocuGuardian</span></div><div className="nav-label">Workspace</div><nav className="nav">{nav.map(([icon, label]) => <button key={label} className={active === label ? "active" : ""} onClick={() => setActive(label)}><span className="nav-icon">{icon}</span><span>{label}</span></button>)}</nav><div className="sidebar-bottom"><div className="user"><span className="avatar">{initials(session.user.name)}</span><div><b>{session.user.name}</b><small>{session.user.role} · {session.user.email}</small></div></div><button className="signout" onClick={signOut}>Sign out</button></div></aside>
    <main className="main"><header className="topbar"><div className="crumb">Workspace / <strong>{active}</strong></div><div className="top-actions"><span className="avatar">{initials(session.user.name)}</span></div></header><section className="content">{currentPage}</section></main>
    {uploadOpen && <div className="upload-modal" role="dialog" aria-modal="true"><div className="modal"><div className="modal-head"><h2>Upload a document</h2><button className="close" onClick={() => setUploadOpen(false)} aria-label="Close">×</button></div><div className="drop" onDragOver={event => event.preventDefault()} onDrop={onDrop}><div className="drop-icon">↑</div><strong>Drop your document here</strong><p>We’ll analyze risks, deadlines, clauses, and recommendations.</p><label className="browse">Browse files<input type="file" accept=".pdf,.docx,.png,.jpg,.jpeg" onChange={onFileChange} /></label></div><div className="format">Supported: PDF, DOCX, JPG, PNG · Max file size 25 MB</div>{uploadError && <p className="form-error">{uploadError}</p>}</div></div>}
    {processing && <ProcessingModal processing={processing} />}
  </div>;
}

function initials(name: string) { return name.split(/\s+/).map(part => part[0]).join("").slice(0, 2).toUpperCase(); }

function AuthScreen({ onAuthenticated }: { onAuthenticated: (session: Session) => void }) {
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
    const response = await fetch(`${API_URL}/api/v1/auth/demo`); if (!response.ok) { setError("Demo access is disabled."); return; }
    const data = await response.json(); window.localStorage.setItem("docuguardian_token", data.access_token); onAuthenticated({ token: data.access_token, user: data.user });
  }
  return <div className="auth-shell"><div className="auth-card card"><div className="brand auth-brand"><span className="brand-mark">D</span><span>DocuGuardian</span></div><h1>{mode === "login" ? "Welcome back" : "Create your workspace"}</h1><p className="auth-subtitle">Understand important documents before they become problems.</p><form onSubmit={submit}>{mode === "register" && <label>Name<input value={name} onChange={event => setName(event.target.value)} required minLength={2} /></label>}<label>Email<input type="email" value={email} onChange={event => setEmail(event.target.value)} required /></label><label>Password<input type="password" value={password} onChange={event => setPassword(event.target.value)} required minLength={8} /></label>{error && <p className="form-error">{error}</p>}<button className="primary auth-submit" disabled={busy}>{busy ? "Please wait…" : mode === "login" ? "Sign in" : "Create account"}</button></form><button className="text-button" onClick={() => { setMode(mode === "login" ? "register" : "login"); setError(""); }}>{mode === "login" ? "Create a new account" : "Already have an account? Sign in"}</button><button className="demo-button" onClick={demo}>Use local demo account</button></div></div>;
}

function Dashboard({ docs, deadlines, analytics, loading, onUpload, onOpenDocuments, onOpenChat }: { docs: DocumentItem[]; deadlines: Deadline[]; analytics: Analytics | null; loading: boolean; onUpload: () => void; onOpenDocuments: () => void; onOpenChat: () => void }) {
  const protection = analytics ? Math.max(0, 100 - analytics.average_risk_score) : 0;
  return <><div className="intro"><div><h1>Good morning</h1><p>Here’s what’s happening with your documents.</p></div><button className="primary" onClick={onUpload}>＋ Upload document</button></div><div className="stats"><Stat icon="▤" label="Documents uploaded" value={analytics ? String(analytics.documents_uploaded) : "—"} foot="Persisted in workspace" /><Stat icon="!" label="High risk documents" value={analytics ? String(analytics.high_risk_documents) : "—"} foot="Needs your attention" tone="red" /><Stat icon="◷" label="Upcoming deadlines" value={analytics ? String(analytics.upcoming_deadlines) : "—"} foot="Extracted from documents" tone="orange" /><Stat icon="✓" label="Protection score" value={analytics ? `${protection}%` : "—"} foot="Based on average risk" tone="green" /></div>{loading ? <EmptyState title="Loading workspace" text="Fetching your documents and deadlines…" /> : <div className="grid"><div className="card docs"><div className="panel-head"><h2>Recent documents</h2><button className="view" onClick={onOpenDocuments}>View all →</button></div>{docs.length ? docs.slice(0, 6).map(doc => <DocumentRow key={doc.id} doc={doc} />) : <EmptyState title="No documents yet" text="Upload a document to start your first analysis." action={onUpload} actionLabel="Upload document" />}</div><div><div className="card deadline"><div className="panel-head"><h2>Upcoming deadlines</h2><button className="view" onClick={() => undefined}>Calendar →</button></div>{deadlines.length ? deadlines.slice(0, 5).map(deadline => <DeadlineRow key={deadline.id} deadline={deadline} />) : <EmptyState title="No deadlines found" text="Deadlines will appear here when they are extracted from a report." />}</div><div className="insight"><h3>✦ Evidence-backed workspace</h3><p>Open an analyzed report to review source evidence, confidence, deadlines, and recommendations.</p><button onClick={onOpenChat}>Ask DocuGuardian →</button></div></div></div>}</>;
}

function WorkspaceScreen({ active, docs, deadlines, analytics, apiUrl, token, onUpload, onRefresh }: { active: string; docs: DocumentItem[]; deadlines: Deadline[]; analytics: Analytics | null; apiUrl: string; token: string; onUpload: () => void; onRefresh: () => void }) {
  const [report, setReport] = useState<Report | null>(null); const [reportDoc, setReportDoc] = useState<DocumentItem | null>(null); const [question, setQuestion] = useState(""); const [selectedChatDoc, setSelectedChatDoc] = useState(""); const [messages, setMessages] = useState<Array<{ role: "ai" | "user"; text: string; citations?: Array<{ label: string; page?: number; confidence?: number }> }>>([{ role: "ai", text: "Ask a question about an analyzed document and I’ll cite the evidence used." }]); const [compareIds, setCompareIds] = useState(["", ""]); const [comparison, setComparison] = useState<Record<string, unknown> | null>(null); const [error, setError] = useState("");
  const analyzedDocs = docs.filter(doc => doc.status === "completed");
  useEffect(() => { if (!selectedChatDoc && analyzedDocs[0]) setSelectedChatDoc(analyzedDocs[0].id); if (!compareIds[0] && analyzedDocs[0]) setCompareIds([analyzedDocs[0].id, analyzedDocs[1]?.id || analyzedDocs[0].id]); }, [analyzedDocs, selectedChatDoc, compareIds]);
  async function openReport(doc: DocumentItem) { setError(""); const response = await apiFetch(`/api/v1/documents/${doc.id}/report`, token); if (!response.ok) { setError("The report is not ready yet."); return; } setReport(await response.json()); setReportDoc(doc); }
  async function ask(text = question) { if (!text.trim() || !selectedChatDoc) return; setQuestion(""); setMessages(items => [...items, { role: "user", text }]); const response = await apiFetch(`/api/v1/documents/${selectedChatDoc}/chat`, token, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ message: text }) }); if (!response.ok) { setError("Chat is unavailable for this document."); return; } const answer = await response.json(); setMessages(items => [...items, { role: "ai", text: answer.answer, citations: answer.citations }]); }
  async function compare() { if (!compareIds[0] || !compareIds[1]) return; const response = await apiFetch("/api/v1/comparisons", token, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ document_a_id: compareIds[0], document_b_id: compareIds[1] }) }); if (response.ok) setComparison(await response.json()); }
  async function remind(id: string) { await apiFetch(`/api/v1/deadlines/${id}/reminders`, token, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ channel: "in_app", days_before: 7 }) }); }
  const titles: Record<string, [string, string]> = { Documents: ["Document library", "Review every file, finding, and obligation in one place."], "AI Chat": ["Ask your documents", "Grounded answers with source citations, not guesses."], Calendar: ["Deadline calendar", "Stay ahead of renewals, payments, and notice periods."], Compare: ["Document comparison", "Compare evidence-backed reports without fabricated differences."], Analytics: ["Workspace analytics", "A clear view of persisted document risk and deadlines."], Settings: ["Workspace settings", "Review your account and organization context."] };
  const [title, subtitle] = titles[active] || titles.Documents;
  return <><div className="workspace-head"><div><h1>{title}</h1><p>{subtitle}</p></div>{active === "Documents" && <button className="primary" onClick={onUpload}>＋ Upload document</button>}</div>{error && <p className="form-error">{error}</p>}{active === "Documents" && <div className="workspace-grid"><div className="card workspace-card"><h2>All documents <span className="muted-count">({docs.length})</span></h2>{docs.length ? docs.map(doc => <div className="doc-row" key={doc.id}><DocumentRow doc={doc} compact /><button className="view" onClick={() => openReport(doc)} disabled={doc.status !== "completed"}>Report →</button></div>) : <EmptyState title="No documents yet" text="Upload a document to begin." action={onUpload} actionLabel="Upload document" />}</div><ReportPanel report={report} reportDoc={reportDoc} apiUrl={apiUrl} token={token} /></div>}{active === "AI Chat" && <div className="chat-shell"><div className="card chat-box"><div className="chat-toolbar"><label>Document<select value={selectedChatDoc} onChange={event => setSelectedChatDoc(event.target.value)}><option value="">Select an analyzed document</option>{analyzedDocs.map(doc => <option key={doc.id} value={doc.id}>{doc.name}</option>)}</select></label></div><div className="messages">{messages.map((message, index) => <div className={`message ${message.role}`} key={index}><div>{message.text}</div>{message.citations?.map((citation, citationIndex) => <span className="citation" key={citationIndex}>▣ {citation.label}{citation.page ? ` · p.${citation.page}` : ""}</span>)}</div>)}</div><div className="chat-input"><input value={question} onChange={event => setQuestion(event.target.value)} onKeyDown={event => event.key === "Enter" && ask()} placeholder="Ask about your documents…" /><button className="primary" onClick={() => ask()}>Send</button></div></div><div className="card workspace-card"><h2>Suggested prompts</h2>{prompts.map(prompt => <button className="prompt" key={prompt} onClick={() => ask(prompt)}>{prompt} <span>→</span></button>)}<p className="disclaimer">Decision support only. Confirm important decisions with a qualified professional.</p></div></div>}{active === "Calendar" && <div className="workspace-grid"><div className="card workspace-card"><h2>Upcoming events</h2>{deadlines.length ? deadlines.map(item => <div className="timeline-item" key={item.id}><span className="timeline-dot" /><div><strong>{item.title}</strong><small>{formatDate(item.due_date)} · {item.priority} priority · {item.source}</small></div><button className="view" onClick={() => remind(item.id)}>Remind me</button></div>) : <EmptyState title="No deadlines found" text="Upload and analyze documents to extract dates." />}</div><div className="card workspace-card"><h2>Reminder channels</h2><p className="report-summary">In-app reminders can be scheduled from extracted deadlines. Email delivery requires a configured notification provider.</p><button className="primary" onClick={onRefresh}>Refresh deadlines</button></div></div>}{active === "Compare" && <ComparisonScreen docs={analyzedDocs} compareIds={compareIds} setCompareIds={setCompareIds} compare={compare} comparison={comparison} />}{active === "Analytics" && <AnalyticsScreen analytics={analytics} />}{active === "Settings" && <div className="card workspace-card"><h2>Workspace settings</h2><p className="report-summary">Account, organization, notification, and security administration are now scoped to the authenticated workspace. Organization member management and external integrations are planned after the core MVP.</p></div>}</>;
}

function ReportPanel({ report, reportDoc, apiUrl, token }: { report: Report | null; reportDoc: DocumentItem | null; apiUrl: string; token: string }) { if (!report || !reportDoc) return <div className="card workspace-card"><h2>Intelligence report</h2><p className="report-summary">Select an analyzed document to review its summary, risks, deadlines, recommendations, and source evidence.</p></div>; return <div className="card workspace-card report-panel"><div className="report-header"><h2>{reportDoc.name}</h2><a className="view" href={`${apiUrl}/api/v1/documents/${reportDoc.id}/report/download`} onClick={event => { if (token) { event.preventDefault(); apiFetch(`/api/v1/documents/${reportDoc.id}/report/download`, token).then(async response => { const blob = await response.blob(); const url = URL.createObjectURL(blob); const link = document.createElement("a"); link.href = url; link.download = `${reportDoc.name}-report.json`; link.click(); URL.revokeObjectURL(url); }); } }}>Download report</a></div><div className="metric"><strong>{report.risk_score}</strong><small>{report.risk_level} risk · {report.classification} · confidence {Math.round(report.confidence * 100)}%</small></div><p className="report-summary">{report.summary}</p><h3>Risk analysis</h3>{report.risks.length ? report.risks.map((risk, index) => <div className="finding" key={`${risk.title}-${index}`}><div className="finding-top"><strong>{risk.title}</strong><span className={`pill ${risk.severity}`}>{risk.severity}</span></div><p>{risk.explanation}</p><small>{risk.recommendation}</small><div className="citation">{risk.source}{risk.page ? ` · page ${risk.page}` : ""}{risk.confidence ? ` · ${Math.round(risk.confidence * 100)}% confidence` : ""}</div></div>) : <p className="muted">No risks were extracted.</p>}<h3>Deadlines</h3>{report.deadlines.length ? report.deadlines.map(deadline => <div className="timeline-item" key={`${deadline.title}-${deadline.date}`}><span className="timeline-dot" /><div><strong>{deadline.title}</strong><small>{formatDate(deadline.date)} · {deadline.priority} priority · {deadline.source}</small></div></div>) : <p className="muted">No deadlines were extracted.</p>}<h3>Recommendations</h3>{report.recommendations.length ? report.recommendations.map(item => <div className="timeline-item" key={item}><span className="timeline-dot" /><div><strong>{item}</strong><small>Evidence-backed action</small></div></div>) : <p className="muted">No recommendations were extracted.</p>}</div>; }

function ComparisonScreen({ docs, compareIds, setCompareIds, compare, comparison }: { docs: DocumentItem[]; compareIds: string[]; setCompareIds: (ids: string[]) => void; compare: () => void; comparison: Record<string, unknown> | null }) { const list = (value: unknown) => Array.isArray(value) ? value.map(String) : []; return <div className="card workspace-card"><h2>Select two analyzed documents</h2>{docs.length < 2 ? <EmptyState title="Two analyzed documents required" text="Upload and complete analysis for another document before comparing." /> : <><div className="comparison"><select value={compareIds[0]} onChange={event => setCompareIds([event.target.value, compareIds[1]])}>{docs.map(doc => <option key={doc.id} value={doc.id}>{doc.name}</option>)}</select><select value={compareIds[1]} onChange={event => setCompareIds([compareIds[0], event.target.value])}>{docs.map(doc => <option key={doc.id} value={doc.id}>{doc.name}</option>)}</select></div><button className="primary" style={{ marginTop: 16 }} onClick={compare}>Compare documents</button>{comparison && <div className="comparison-result"><div className="metric"><strong>{String(comparison.similarity_score)}%</strong><small>report similarity</small></div><div className="comparison"><div className="comparison-col"><h3>Added risks</h3>{list(comparison.added_risks).map(item => <p key={item}>＋ {item}</p>)}<h3>Added deadlines</h3>{list(comparison.added_deadlines).map(item => <p key={item}>＋ {item}</p>)}</div><div className="comparison-col"><h3>Removed risks</h3>{list(comparison.removed_risks).map(item => <p key={item}>− {item}</p>)}<h3>Removed deadlines</h3>{list(comparison.removed_deadlines).map(item => <p key={item}>− {item}</p>)}</div></div></div>}</>}</div>; }

function AnalyticsScreen({ analytics }: { analytics: Analytics | null }) { if (!analytics) return <EmptyState title="Analytics unavailable" text="Analytics will appear after the workspace loads." />; const total = Math.max(analytics.documents_uploaded, 1); return <div className="workspace-grid"><div className="card workspace-card"><h2>Risk distribution</h2><div className="chart-row"><div className="bar" style={{ height: `${Math.max(6, analytics.high_risk_documents / total * 100)}%` }}><span>{analytics.high_risk_documents}</span></div><div className="bar" style={{ height: `${Math.max(6, analytics.medium_risk_documents / total * 100)}%`, background: "linear-gradient(#f8c75e,#f59e0b)" }}><span>{analytics.medium_risk_documents}</span></div><div className="bar" style={{ height: `${Math.max(6, analytics.low_risk_documents / total * 100)}%`, background: "linear-gradient(#53d3a5,#10b981)" }}><span>{analytics.low_risk_documents}</span></div></div><div className="chart-labels"><span>High risk</span><span>Medium</span><span>Low risk</span></div></div><div className="card workspace-card"><h2>Workspace health</h2><div className="stats analytics-stats"><Stat icon="▤" label="Documents" value={String(analytics.documents_uploaded)} foot="total" /><Stat icon="!" label="Avg. risk" value={String(analytics.average_risk_score)} foot="out of 100" tone="orange" /><Stat icon="◷" label="Deadlines" value={String(analytics.upcoming_deadlines)} foot="upcoming" tone="green" /></div></div></div>; }

function DocumentRow({ doc, compact = false }: { doc: DocumentItem; compact?: boolean }) { const type = doc.name.split(".").pop()?.toUpperCase() || "FILE"; return <><div className={`file-icon ${type === "PDF" ? "pdf" : ""}`}>{type}</div><div><div className="doc-title">{doc.name}</div><div className="doc-meta">{doc.classification || type} · {formatDate(doc.created_at)}</div></div><div className={`risk ${doc.risk_level || "low"}`}><span className="risk-dot" />{doc.status === "completed" ? `${doc.risk_level || "unknown"} · ${doc.risk_score ?? "—"}` : doc.status === "failed" ? "Failed" : `${doc.stage || "Queued"} · ${doc.progress}%`}</div>{!compact && <div className="status">{doc.status}</div>}</>; }
function DeadlineRow({ deadline }: { deadline: Deadline }) { return <div className="deadline-item"><div className="date-box"><strong>{new Date(deadline.due_date).getUTCDate()}</strong>{new Date(deadline.due_date).toLocaleString("en", { month: "short", timeZone: "UTC" }).toUpperCase()}</div><div><div className="deadline-title">{deadline.title}</div><div className="deadline-meta">{formatDate(deadline.due_date)} · {deadline.priority} priority</div></div></div>; }
function ProcessingModal({ processing }: { processing: { name: string; progress: number; stage: string; stages: Stage[] } }) { return <div className="upload-modal"><div className="modal processing-modal"><div className="drop-icon">✦</div><h2>Analyzing {processing.name}</h2><p>Processing is running in the document pipeline.</p><div className="score-track"><div className="score-fill" style={{ width: `${processing.progress}%` }} /></div><strong>{processing.progress}% · {processing.stage}</strong><div className="stage-list">{processing.stages.map(stage => <div key={stage.stage} className={stage.status}><span>{stage.status === "completed" ? "✓" : stage.status === "running" ? "•" : "○"}</span>{stage.stage}</div>)}</div></div></div>; }
function Stat({ icon, label, value, foot, tone }: { icon: string; label: string; value: string; foot: React.ReactNode; tone?: string }) { return <div className="card stat"><div className="stat-top"><span>{label}</span><span className="stat-icon" data-tone={tone}>{icon}</span></div><div className="stat-value">{value}</div><div className="stat-foot">{foot}</div></div>; }
function EmptyState({ title, text, action, actionLabel }: { title: string; text: string; action?: () => void; actionLabel?: string }) { return <div className="empty-state"><strong>{title}</strong><p>{text}</p>{action && <button className="view" onClick={action}>{actionLabel || "Try again"}</button>}</div>; }
function formatDate(value: string) { const date = new Date(value); return Number.isNaN(date.getTime()) ? value : date.toLocaleDateString(); }
