# DocuGuardian -- UI/UX Design Specification

## Vision

Build an AI Document Intelligence Platform that proactively understands,
analyzes, protects, and guides users through important documents.

------------------------------------------------------------------------

# 1. Design Principles

-   **Simple** -- Non-technical users should understand everything.
-   **Proactive** -- AI should surface insights automatically.
-   **Trustworthy** -- Use risk colors, explanations, and transparency.
-   **Action-Oriented** -- Every insight should suggest a next step.
-   **Responsive** -- Mobile-first with desktop enhancements.

------------------------------------------------------------------------

# 2. Design System

## Color Palette

  Purpose      Color
  ------------ -----------
  Primary      `#2563EB`
  Secondary    `#4F46E5`
  Success      `#10B981`
  Warning      `#F59E0B`
  Critical     `#EF4444`
  Background   `#F8FAFC`
  Card         `#FFFFFF`

## Typography

-   Font: Inter
-   Headings: 700
-   Body: 400--500

## Border Radius

-   Cards: 16px
-   Buttons: 12px
-   Inputs: 12px

------------------------------------------------------------------------

# 3. User Journey

``` text
Landing Page
      │
      ▼
Sign In
      │
      ▼
Dashboard
      │
      ▼
Upload Document
      │
      ▼
AI Processing Pipeline
      │
      ▼
Document Intelligence Report
      │
      ├── AI Chat
      ├── Calendar
      ├── Compare
      └── Analytics
```

------------------------------------------------------------------------

# 4. Landing Page

## Hero

-   Headline: **Protect Every Document Before It Costs You**
-   Subheading: Upload contracts, insurance, medical reports, rental
    agreements and receive AI-powered insights.
-   CTA:
    -   Upload Document
    -   Watch Demo

## Feature Grid

-   Smart Summary
-   Risk Detection
-   Deadline Tracking
-   AI Assistant
-   Contract Comparison
-   Voice Summary

------------------------------------------------------------------------

# 5. Dashboard

## Sidebar

-   Dashboard
-   Documents
-   AI Chat
-   Calendar
-   Compare
-   Analytics
-   Settings

## Top Summary Cards

-   Documents Uploaded
-   High Risk Documents
-   Upcoming Deadlines
-   Protection Score

## Recent Documents

Each card displays: - Document Name - Risk Score - Status - Upload Date

------------------------------------------------------------------------

# 6. Upload Screen

## Features

-   Drag & Drop
-   Browse Files
-   PDF
-   DOCX
-   Images
-   Scanned Documents

------------------------------------------------------------------------

# 7. AI Processing Screen

Animated Pipeline

1.  OCR
2.  Parsing
3.  Classification
4.  Clause Extraction
5.  Risk Analysis
6.  Deadline Detection
7.  Recommendation Generation
8.  AI Report Generation

------------------------------------------------------------------------

# 8. Document Intelligence Report

## Header

-   Document Name
-   Risk Score
-   Classification
-   Download Report

## Sections

### Plain Language Summary

-   Key Information
-   Important Dates
-   Coverage / Duration
-   Parties

### Risk Analysis

Severity Levels

-   Critical
-   High
-   Medium
-   Low

Each risk includes: - Clause - Explanation - Recommendation

### Timeline

-   Upload Date
-   Review Date
-   Renewal Date
-   Expiry
-   Payment Due

### AI Recommendations

Examples:

-   Review Clause 12
-   Negotiate penalty clause
-   Save payment receipt
-   Contact provider

------------------------------------------------------------------------

# 9. AI Chat

## Layout

Left Panel

-   Conversation

Right Panel

-   Document Viewer

Suggested Prompts

-   Explain Like I'm 15
-   Show Hidden Risks
-   Find Deadlines
-   Summarize
-   Compare With Standard Contract

------------------------------------------------------------------------

# 10. Contract Comparison

Split Screen

Left

-   Contract A

Right

-   Contract B

Highlights

-   Green → Same
-   Yellow → Modified
-   Red → Added Risk

Metrics

-   Similarity Score
-   New Risks
-   Removed Clauses

------------------------------------------------------------------------

# 11. Calendar

Displays

-   Renewals
-   EMI Dates
-   Expiry Dates
-   Warranty End
-   Notice Period

Supports

-   Google Calendar
-   Outlook
-   Email Reminder
-   Push Notification

------------------------------------------------------------------------

# 12. Analytics

KPIs

-   Total Documents
-   Average Risk Score
-   High Risk Documents
-   Upcoming Deadlines

Charts

-   Risk Distribution
-   Document Categories
-   Monthly Uploads

------------------------------------------------------------------------

# 13. AI Agents

## Risk Analyst

Detects: - Hidden penalties - Liability - Termination clauses -
Auto-renewal

## Legal Simplifier

Explains: - Legal language - Complex clauses - User rights

## Deadline Agent

Extracts: - Expiry - Renewal - Payment - Notice period

## Action Planner

Generates: - Checklist - Negotiation tips - Emails - Required documents

## Fraud Detector (Future)

Detects: - Suspicious wording - Missing signatures - Formatting
inconsistencies

------------------------------------------------------------------------

# 14. Mobile UI

Bottom Navigation

-   Dashboard
-   Upload
-   Chat
-   Calendar
-   Profile

Swipe Cards

-   Summary
-   Risks
-   Deadlines
-   Recommendations

------------------------------------------------------------------------

# 15. UX Micro-interactions

-   Animated upload
-   Live AI pipeline
-   Interactive PDF highlighting
-   Click clause to navigate
-   Voice playback
-   Risk gauge animation
-   Confetti on analysis completion
-   Floating AI assistant

------------------------------------------------------------------------

# 16. Recommended Tech Stack

  Layer        Technology
  ------------ ------------------------------
  Frontend     Next.js + React + TypeScript
  UI           Tailwind CSS + shadcn/ui
  Animation    Framer Motion
  Icons        Lucide React
  Charts       Recharts
  PDF Viewer   React PDF Viewer
  Backend      FastAPI
  OCR          PaddleOCR / Tesseract
  LLM          GPT-5.5 / Gemini / Claude
  Vector DB    pgvector / FAISS
  Database     PostgreSQL
  Storage      AWS S3
  Auth         Clerk / Auth.js
  Deployment   Vercel + Railway

------------------------------------------------------------------------

# 17. Hackathon Differentiators

-   AI Intelligence Dashboard instead of a basic chatbot
-   Proactive risk detection
-   Clickable clause explanations
-   Contract comparison
-   Calendar integration
-   Action plans
-   Voice summaries
-   End-to-end AI workflow
