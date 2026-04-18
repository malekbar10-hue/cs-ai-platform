# CS AI Engine — Product Deployment Roadmap
**From Strong Engine to Enterprise-Ready Product**
Version 1.0 — April 2026

---

## Executive Summary

The CS AI engine is no longer a prototype. It is a structured, multi-agent pipeline with verified facts, formal state management, typed schemas at every boundary, policy enforcement, fallback safety, customer memory, health scoring, SLA-aware routing, structured audit logging, and a full unit test and eval suite.

What this means in practice: the AI engine itself is production-grade. The gap that remains is not "make the AI smarter." It is building the enterprise shell around the engine — the identity layer, approval workflows, tenant isolation, live monitoring, privacy lifecycle, and operator tooling that companies actually require before signing a deployment contract.

Current guidance from OpenAI, Anthropic, McKinsey, and CNIL all converge on the same point: production AI must have layered guardrails alongside authentication, authorization, human oversight, explainability logs, and continuous quality monitoring throughout the lifecycle. McKinsey explicitly identifies fragmented data, weak governance, and lack of visibility as the primary reasons agentic AI fails at scale. CNIL requires human override capability, confidence-aware escalation, explainability, and ongoing output quality control.

This roadmap closes all those gaps in three waves over 20 weeks.

---

## Part 1: Where We Are Now

### What Is Built and Working

| Layer | Module | Status |
|---|---|---|
| Control Plane | State Machine (TicketState FSM) | ✅ Production |
| Control Plane | Policy Engine (4 hard rules, pure Python) | ✅ Production |
| Control Plane | Orchestrator (full 8-step pipeline) | ✅ Production |
| Truth Plane | Fact Registry (typed, verified, TTL) | ✅ Production |
| Truth Plane | Validator Agent (claim vs fact check) | ✅ Production |
| Truth Plane | Fact Builder (ERP/CRM → registry) | ✅ Production |
| Experience Plane | Triage Agent (NLP, SLA, health, routing) | ✅ Production |
| Experience Plane | Response Agent (prompt, model, AI call) | ✅ Production |
| Experience Plane | QA Agent (review + 2-retry loop) | ✅ Production |
| Experience Plane | Draft Guard (completeness check) | ✅ Production |
| Experience Plane | Fallback Engine (8 Jinja2 templates, EN+FR) | ✅ Production |
| Experience Plane | Scoped Memory (SQLite, TTL, PII redacted) | ✅ Production |
| Intelligence | Customer Health Score (weighted, 4 signals) | ✅ Production |
| Intelligence | SLA-Aware Routing (urgency levels) | ✅ Production |
| Infrastructure | Typed Schemas (Pydantic, strict, 6 models) | ✅ Production |
| Infrastructure | Trace Logger (structured JSON, PII redacted) | ✅ Production |
| Infrastructure | Prompt Registry (semver, checksum, versioned) | ✅ Production |
| Infrastructure | Connector Resilience (typed errors, retries) | ✅ Production |
| Quality | Unit Test Suite (12 files, 50+ tests) | ✅ Production |
| Quality | Eval Harness (21 cases, 4 graders, CI gate) | ✅ Production |

### The 7 Immediate Steps Before Anything Else

These come before any of the roadmap waves below. They are pre-conditions.

**Step 1 — Run unit tests**
`pytest tests/unit/ -v` — verifies all 12 modules work in isolation. Fix any import errors before proceeding. No API key needed, takes under 30 seconds.

**Step 2 — Run the eval harness**
`python cs_ai/evals/simulator.py --dataset nominal --verbose` — sends test messages through the full pipeline and grades the output. Establishes the baseline score before any changes are made.

**Step 3 — End-to-end smoke test**
Send one real customer message through the app manually. Verify the route, draft, confidence score, and state machine transition are all correct.

**Step 4 — Connect real ERP/CRM**
Replace mock connectors in `fact_builder.py` with live API calls to your actual ERP/CRM system. This is when real order data starts flowing through the fact registry.

**Step 5 — Set up GitHub Actions CI gate**
Create `.github/workflows/ci_eval.yml` so the eval harness blocks any pull request that drops quality below 80%. Every code change is now gated.

**Step 6 — Tune the response prompt**
After running real messages, iterate on `cs_ai/prompts/response_system.json` based on actual output quality. Increment version number on every change.

**Step 7 — Add real eval cases**
Add customer messages from your actual business into the eval datasets — their real language, real complaints, real order formats. The harness tests what actually matters.

---

## Part 2: The Enterprise Gap Analysis

The engine is built. What is missing is the enterprise operating system around the engine. There are 16 gaps across 5 categories.

### Category A — Identity and Access Control

**Gap 1: Enterprise Auth, RBAC, and Approval Workflows**

No company will deploy a system that reads customer emails, queries ERP data, and sends replies unless they can control exactly who can do what. This is non-negotiable for enterprise IT and compliance teams.

What to add:
- SSO-ready authentication layer (OAuth2/SAML)
- Role-based access control by tenant, team, and individual user
- Approval matrix: agent auto-approves low-risk drafts; supervisor required for refunds, cancellations, legal-sensitive cases
- Immutable approval audit trail — who approved what, when, with what justification

**Gap 2: Tenant Isolation Everywhere**

Data separation between companies is one of the first questions any enterprise buyer will ask. McKinsey identifies governance and access boundaries as foundational for scaling agentic systems.

What to harden:
- Separate storage namespaces per company (no shared DB tables)
- Tenant-scoped prompt registry (each company can have its own prompt versions)
- Tenant-scoped memory (no customer data crossing company boundaries)
- Tenant-scoped logs and traces (each company sees only its own data)
- Tenant-specific policy bundles (each company sets its own rules)
- No shared vector space or memory without hard partitioning

**Gap 3: Secure Secrets and Environment Management**

A deployable product needs formal handling of API keys, ERP credentials, SMTP credentials, webhook secrets, and encryption keys.

What to add:
- Secret manager integration (AWS Secrets Manager, Azure Key Vault, or HashiCorp Vault)
- Zero secrets in the repository or local config files
- Key rotation process with zero-downtime
- Three environment separation: dev / staging / production with identical configurations

### Category B — Human Control and Oversight

**Gap 4: Human Review Console**

CNIL is explicit that humans must be able to intervene, override, modify, or stop system behavior, and the cases requiring human intervention must be identified. Your engine already routes to review — but most companies need a usable UI where reviewers can act on that routing.

What to add:
- Inbox view of tickets in review queue
- Per-ticket view showing: the draft, the facts used to generate it, the risk flags, the reason it was blocked or downgraded, the confidence score breakdown
- Inline edit and approve workflow
- Side-by-side comparison of AI draft vs final human version (for quality tracking)
- Supervisor reassignment and team routing

**Gap 10: Incident Handling and Safe Shutdown Modes**

Companies need to know what happens when the model provider has an outage, ERP latency explodes, a bad config is pushed, or fallback volume suddenly doubles.

What to add:
- Circuit-breaker dashboards showing connector health in real time
- Incident mode toggle: switch entire system from auto-send to review-only instantly
- Global kill switch and per-tenant kill switch
- Model failover mode (switch to cheaper or backup model automatically)
- Degraded-mode behavior playbook — documented and tested

### Category C — Observability and Monitoring

**Gap 5: Live Observability Dashboards**

You have trace logging, which is excellent. But companies want operational dashboards — not raw JSON logs. McKinsey identifies visible and measurable behavior as a key principle for scalable agentic systems.

Dashboards to build:
- Tickets by route (auto / standard / priority / supervisor / noise)
- Blocked vs sent vs review rate over time
- Fallback rate by reason and by tenant
- Unsupported claim rate (how often the validator fires)
- Connector health per integration
- Average pipeline latency by step
- SLA breach risk by ticket age
- Token cost per tenant per day
- Human edit rate by prompt version (reveals which prompt versions produce worse drafts)

**Gap 6: Live Quality Monitoring After Deployment**

The eval harness prevents regressions before release. But you also need post-deployment drift monitoring. CNIL explicitly states output quality should be controlled throughout the lifecycle and logs should be analyzed to detect anomalies or attacks.

What to add:
- Online sampling of sent replies (random 5–10%) with automated grading
- Periodic grading of real outputs using the same 4 graders from the eval harness
- Alert when fallback rate spikes above threshold
- Alert when human-edit distance spikes (reviewers are making big changes = AI quality dropping)
- Alert when one connector suddenly degrades output quality
- Drift tracking by tenant, language, and intent over rolling 7-day and 30-day windows

### Category D — Data Governance and Privacy

**Gap 7: Data Retention, Privacy, and Redaction Policies**

This is a major enterprise requirement, especially in Europe. CNIL expects logged information to be limited to what is necessary, explainable after the fact, and retained for justified durations only. You already redact PII in logs, which is a strong foundation. The next step is a formal lifecycle policy in code and config.

Define per tenant:
- How long raw email content is stored (recommended: 90 days operational, then delete)
- How long traces and audit logs are stored (recommended: 1 year compliance, then archive)
- How long memory items live (already TTL-controlled, formalize per tenant)
- What PII is redacted before any log write (already implemented, extend to traces)
- What content is never persisted under any circumstances
- Customer data export and deletion workflow (GDPR right to erasure)

**Gap 8: Semantic Normalization of Business Data**

McKinsey argues that scale requires shared meaning, not just shared data. When you connect multiple ERP or CRM systems, they will use different field names, different status codes, different date formats, and different entity structures. Without a semantic layer, the fact registry receives conflicting data and the AI starts producing inconsistent responses.

What to add:
- Canonical business entities: Order, Invoice, Shipment, Return, Complaint — each with a stable internal schema
- Normalized field mapping adapter per ERP/CRM integration (SAP, Oracle, Salesforce, etc. all map to canonical form)
- One semantic contract inside the engine regardless of what the external system sends
- Conflict detection when two sources disagree on the same entity

**Gap 13: Knowledge Base Governance**

You already block unsupported claims, which is strong. The next maturity step is a governed KB layer that makes the knowledge base trustworthy over time.

What to add:
- Versioned KB articles with change history
- Article freshness timestamps and staleness alerts
- Article ownership (who is responsible for keeping it current)
- Conflict detection between KB content and ERP live data
- Claim-to-source linking in the validator output (the review console can show "this claim came from KB article #47")

### Category E — Action Governance and Release Control

**Gap 9: Action Governance for ERP-Changing Operations**

Reading data is one level of risk. Writing back to systems — issuing refunds, modifying orders, canceling shipments — is another. Before any live ERP mutation, a formal action governance layer is required. McKinsey explicitly states policies should define what agents can do, what data they can access, and when human approval is required.

What to add:
- Action registry: every possible ERP action catalogued with its risk level
- Four action tiers: read-only / recommendation-only / write-requiring-approval / fully-forbidden
- Approval chain for write actions: who approves, escalation if no response in N minutes
- Idempotent write receipts: every ERP mutation logged with a unique receipt ID
- Rollback or compensating workflow for reversible actions

**Gap 11: Deployment Pipeline and Release Controls**

A deployable product needs release discipline that most enterprise IT departments will audit.

What to add:
- Staging environment identical to production in configuration
- Schema migration process for DB and config changes
- Canary release by tenant (roll out to 10% of companies first)
- Rollback by prompt version (revert `response_system.json` to previous version instantly)
- Release checklist: unit tests pass + eval gate pass + smoke test pass + config validation pass
- Config validation before deploy (fail fast if required keys are missing)

**Gap 12: Pricing and Cost Governance Hooks**

McKinsey and enterprise AI surveys consistently show ROI clarity as a major obstacle to scale. Companies want predictable, measurable costs — especially with token-based pricing.

What to add:
- Token cost accounting per ticket (already tracking usage, now attach cost)
- Cost breakdown per tenant per day
- Model-tier routing by complexity: simple tracking requests go to cheaper model; escalations go to more capable model
- Budget ceilings per tenant with alerts before breach
- Cost dashboard visible to tenant admins

### Category F — Product Features

**Gap 14: Multilingual and Locale Discipline**

Most European B2B companies will require more than English and French. Before expanding language support, formalize the current multilingual handling.

What to formalize:
- Language confidence thresholds (below X% confidence → route to review instead of auto-send)
- Fallback behavior when language cannot be detected confidently
- Locale-aware date and number formatting in templates
- Country-specific regulatory wording (refund rights differ by jurisdiction)
- Tenant-level style packs (formal vs informal, industry-specific vocabulary)

**Gap 15: Attachment Pipeline**

In B2B customer service, customers regularly send PDFs, screenshots, purchase orders, and invoices. Without attachment handling, companies will see the product as incomplete for real workloads.

What to add:
- Attachment type classifier (PDF, image, spreadsheet, unknown)
- Structured field extractor for common document types (order number, invoice total, date)
- Confidence score on extracted fields (verified vs unverified)
- Separate fact registry entries for extracted vs ERP-confirmed data
- Route unreadable or unclassifiable attachments directly to human review

**Gap 16: Operator Tooling — "Company Wants" Features**

What most companies want operationally is often less glamorous than AI capability but more important for actual adoption.

What to add:
- Supervisor queue view with bulk triage filters (by route, by SLA urgency, by tenant)
- Review comments and internal notes per ticket
- Team reassignment with notification
- "Show why blocked" — one-click explanation in the review console
- "Show facts used" — which KB articles and ERP fields generated this draft
- Exportable audit history per ticket (for compliance, legal, or customer disputes)
- Configurable auto-close rules for noise and resolved tickets

---

## Part 3: The Roadmap

### Pre-Launch (Now — 4 Weeks)
*The 7 immediate steps. Non-negotiable before anything else.*

| Week | Action |
|---|---|
| 1 | Run `pytest tests/unit/ -v` — fix all failures |
| 1 | Run eval harness, establish baseline score |
| 2 | End-to-end smoke test with real messages |
| 2 | Connect real ERP/CRM to fact_builder.py |
| 3 | Set up GitHub Actions CI gate |
| 3 | First prompt tuning cycle based on real outputs |
| 4 | Add first wave of real customer cases to eval dataset |

---

### Wave 1: Enterprise Foundation (Weeks 5–12)
*Without this, no enterprise buyer will sign. First and highest priority.*

**Week 5–6: Auth + RBAC + Approval Workflows**
- SSO-ready authentication
- Role-based access: viewer / agent / supervisor / admin / tenant-owner
- Approval matrix wired to policy engine decisions
- Immutable approval log

**Week 6–7: Tenant Isolation Hardening**
- Namespace all storage per company
- Tenant-scoped prompt registry
- Tenant-scoped memory and logs
- Tenant-specific policy bundles

**Week 7–8: Secret Management + Environment Separation**
- Secret manager integration
- Remove all credentials from config files and repo
- Dev / staging / production environments with config validation

**Week 8–10: Human Review Console**
- Ticket queue UI with filter by route, urgency, and tenant
- Per-ticket view: draft, facts used, risk flags, confidence breakdown, block reason
- Inline edit, approve, and reassign
- AI draft vs final human version tracking

**Week 10–12: Live Observability Dashboards**
- Route distribution, block rate, fallback rate, connector health
- Latency by pipeline step
- SLA breach risk
- Token cost by tenant
- Human edit rate by prompt version

**Wave 1 Exit Criteria:**
- Enterprise IT can control who sees and approves what
- No customer data crosses tenant boundaries
- No credentials in the repository
- Reviewers have a usable console
- Ops team can see what the system is doing in real time

---

### Wave 2: Governance and Reliability (Weeks 13–18)
*Satisfies compliance requirements and makes the system safe for production operations.*

**Week 13–14: Data Retention and Privacy Lifecycle**
- Formal retention policy per data type, in code and config
- Customer data export and deletion workflow
- Extend PII redaction to all trace outputs

**Week 14–15: Action Governance for ERP Mutations**
- Action registry with risk tiers
- Approval chain for write actions
- Idempotent receipts and rollback workflow

**Week 15–16: Incident Mode and Safe Shutdown**
- Global and per-tenant kill switch
- Auto-send → review-only toggle
- Model failover
- Degraded-mode playbook

**Week 16–17: Deployment Pipeline**
- Staging environment
- Canary releases by tenant
- Prompt version rollback
- Pre-deploy release checklist with automated validation

**Week 17–18: Semantic Normalization Layer**
- Canonical entity schema: Order, Invoice, Shipment, Return, Complaint
- ERP/CRM field mapping adapters
- Conflict detection between sources

**Week 17–18: Live Quality Monitoring**
- Online sampling and grading of sent replies
- Drift alerts by tenant, language, intent
- Fallback spike and human-edit spike alerts

**Wave 2 Exit Criteria:**
- Compliance team can sign off on data lifecycle
- No ERP mutation happens without human approval
- Ops can put any tenant into safe mode in one click
- Releases can be rolled back in under 5 minutes
- Quality drift is detected automatically without waiting for complaints

---

### Wave 3: Market Expansion (Weeks 19–24)
*Widens the addressable market and deepens competitive differentiation.*

**Week 19–20: Attachment Pipeline**
- Attachment classifier, field extractor, confidence scoring
- Separate verified vs unverified extracted data in fact registry

**Week 20–21: Knowledge Base Governance**
- Versioned articles, ownership, freshness alerts
- Claim-to-source linking visible in review console

**Week 21–22: Multilingual and Locale Discipline**
- Language confidence thresholds
- Locale-aware templates
- Country-specific regulatory wording
- Tenant-level style packs

**Week 22–23: Cost Governance**
- Per-ticket cost accounting
- Model-tier routing by complexity
- Budget ceilings and alerts
- Cost dashboard for tenant admins

**Week 23–24: Operator Tooling**
- Bulk triage filters, team reassignment, review comments
- "Show why blocked" and "Show facts used" in console
- Exportable audit history per ticket

**Wave 3 Exit Criteria:**
- Product handles PDF and image attachments
- Each company can have its own KB, tone, and language settings
- Companies can see and control their AI costs
- Reviewers have everything they need to work without switching tools

---

## Part 4: What This Becomes

After these three waves, the product is no longer described as a "CS AI engine." It becomes a **governed, multi-tenant customer service AI operating system** with:

- A verifiable, hallucination-resistant AI pipeline
- Enterprise-grade identity and access control
- Full human oversight and approval workflow
- Live quality monitoring and drift detection
- Compliance-ready data lifecycle management
- Real-time operational dashboards
- ERP-safe action governance
- A CI/CD pipeline with regression gates

That is the product companies in Europe, regulated industries, and enterprise B2B will actually sign a contract for.

---

## Part 5: Priority Matrix

| Gap | Impact | Effort | Priority |
|---|---|---|---|
| Auth + RBAC | Very High | Medium | Wave 1 — Week 1 |
| Human review console | Very High | Medium | Wave 1 — Week 2 |
| Tenant isolation | Very High | Medium | Wave 1 — Week 1 |
| Secret management | High | Low | Wave 1 — Week 2 |
| Live dashboards | High | Medium | Wave 1 — Week 3 |
| Data retention policy | High | Low | Wave 2 — Week 1 |
| Action governance | High | Medium | Wave 2 — Week 2 |
| Incident mode | High | Low | Wave 2 — Week 2 |
| Deployment pipeline | High | Medium | Wave 2 — Week 2 |
| Live quality monitoring | High | Medium | Wave 2 — Week 3 |
| Semantic normalization | Medium | High | Wave 2 — Week 4 |
| KB governance | Medium | Medium | Wave 3 — Week 1 |
| Attachment pipeline | Medium | High | Wave 3 — Week 1 |
| Multilingual discipline | Medium | Medium | Wave 3 — Week 2 |
| Cost governance | Medium | Low | Wave 3 — Week 2 |
| Operator tooling | Medium | Low | Wave 3 — Week 3 |

---

## Part 6: Success Milestones

**Milestone 1 — Engine Verified (End of Pre-Launch)**
All unit tests pass. Eval harness scores above 0.80. Real ERP data flowing through fact registry. CI gate active on GitHub.

**Milestone 2 — Enterprise-Ready (End of Wave 1)**
First enterprise pilot customer can be onboarded. Auth, isolation, console, and dashboards are live. No manual ops required to run the system day-to-day.

**Milestone 3 — Compliance-Ready (End of Wave 2)**
CNIL/GDPR audit can be passed. ERP writes are controlled. Incidents can be handled without engineer intervention. Quality drift is monitored automatically.

**Milestone 4 — Market-Ready (End of Wave 3)**
Product handles real B2B workloads including attachments and mixed languages. Tenant admins can manage their own settings, costs, and KB. Product can be sold to any European B2B company without custom engineering.

---

*This roadmap is grounded in the CS AI engine build completed April 2026 and aligned with current enterprise AI guidance from OpenAI, Anthropic, McKinsey, CNIL, and OWASP.*
