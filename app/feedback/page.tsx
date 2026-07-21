"use client";

import { FormEvent, useMemo, useState } from "react";

const feedbackTypes = ["Product feedback", "Bug report", "Feature idea", "AI response quality", "Other"];
const satisfactionScores = ["1", "2", "3", "4", "5"];

export default function FeedbackPage() {
  const [type, setType] = useState(feedbackTypes[0]);
  const [score, setScore] = useState("5");
  const [message, setMessage] = useState("");
  const [email, setEmail] = useState("");
  const [submitted, setSubmitted] = useState(false);

  const remaining = useMemo(() => Math.max(0, 600 - message.length), [message]);

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const payload = {
      type,
      score,
      message: message.trim(),
      email: email.trim(),
      submitted_at: new Date().toISOString(),
    };
    window.localStorage.setItem("docuguardian_last_feedback", JSON.stringify(payload));
    setSubmitted(true);
  }

  return <main className="feedback-page">
    <section className="feedback-hero">
      <a className="feedback-back" href="/">← Back to DocuGuardian</a>
      <div className="landing-brand feedback-brand"><span className="brand-mark">D</span><span>DocuGuardian</span></div>
      <span className="feedback-kicker">Feedback center</span>
      <h1>Help us improve document protection</h1>
      <p>Tell us what worked, what felt confusing, or which document-risk workflows you want DocuGuardian to handle next.</p>
    </section>

    <section className="feedback-layout">
      <div className="card feedback-card">
        {submitted ? <div className="feedback-success" role="status">
          <div className="feedback-success-icon">✓</div>
          <h2>Thanks for the feedback!</h2>
          <p>Your note was saved in this browser for the DocuGuardian team workflow.</p>
          <button className="primary" onClick={() => { setSubmitted(false); setMessage(""); setEmail(""); }}>Send another response</button>
        </div> : <form onSubmit={submit}>
          <div className="feedback-field">
            <label htmlFor="feedback-type">What are you sharing?</label>
            <select id="feedback-type" value={type} onChange={event => setType(event.target.value)}>
              {feedbackTypes.map(item => <option key={item} value={item}>{item}</option>)}
            </select>
          </div>

          <div className="feedback-field">
            <label>How satisfied are you?</label>
            <div className="feedback-score" aria-label="Satisfaction score">
              {satisfactionScores.map(item => <button key={item} type="button" className={score === item ? "active" : ""} onClick={() => setScore(item)} aria-pressed={score === item}>{item}</button>)}
            </div>
            <small>1 = needs work, 5 = excellent</small>
          </div>

          <div className="feedback-field">
            <label htmlFor="feedback-message">Your feedback</label>
            <textarea id="feedback-message" value={message} onChange={event => setMessage(event.target.value.slice(0, 600))} required minLength={10} placeholder="Example: The risk report helped me find a renewal deadline, but I wanted a clearer next action…" />
            <small>{remaining} characters remaining</small>
          </div>

          <div className="feedback-field">
            <label htmlFor="feedback-email">Email (optional)</label>
            <input id="feedback-email" type="email" value={email} onChange={event => setEmail(event.target.value)} placeholder="you@example.com" />
          </div>

          <button className="primary feedback-submit" disabled={message.trim().length < 10}>Submit feedback</button>
        </form>}
      </div>

      <aside className="feedback-aside">
        <div className="card feedback-tip">
          <h2>What helps most?</h2>
          <ul>
            <li>The document type or workflow you were using.</li>
            <li>What you expected versus what happened.</li>
            <li>Any missing risk, deadline, or clause detail.</li>
          </ul>
        </div>
        <div className="card feedback-tip dark">
          <h2>Privacy reminder</h2>
          <p>Please do not include full Social Security numbers, bank account numbers, or medical record identifiers in feedback.</p>
        </div>
      </aside>
    </section>
  </main>;
}
