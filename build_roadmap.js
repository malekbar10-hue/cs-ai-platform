const {
  Document, Packer, Paragraph, TextRun, Table, TableRow, TableCell,
  Header, Footer, AlignmentType, HeadingLevel, BorderStyle, WidthType,
  ShadingType, VerticalAlign, PageNumber, PageBreak, LevelFormat,
  ExternalHyperlink, TableOfContents
} = require('docx');
const fs = require('fs');

// ── helpers ──────────────────────────────────────────────────────────────────
const BORDER = { style: BorderStyle.SINGLE, size: 1, color: "CCCCCC" };
const BORDERS = { top: BORDER, bottom: BORDER, left: BORDER, right: BORDER };
const NO_BORDER = { style: BorderStyle.NONE, size: 0, color: "FFFFFF" };
const NO_BORDERS = { top: NO_BORDER, bottom: NO_BORDER, left: NO_BORDER, right: NO_BORDER };

const BLUE_DARK  = "1F3864";
const BLUE_MID   = "2E75B6";
const BLUE_LIGHT = "D5E8F0";
const BLUE_PALE  = "EBF3FB";
const RED        = "C00000";
const ORANGE     = "C55A11";
const GREEN      = "375623";
const GREEN_FILL = "E2EFDA";
const ORANGE_FILL= "FCE4D6";
const RED_FILL   = "FFE9E9";
const YELLOW_FILL= "FFF2CC";
const GRAY_FILL  = "F2F2F2";

function h1(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_1,
    children: [new TextRun({ text, font: "Arial", size: 36, bold: true, color: BLUE_DARK })],
    spacing: { before: 400, after: 200 },
  });
}
function h2(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_2,
    children: [new TextRun({ text, font: "Arial", size: 28, bold: true, color: BLUE_MID })],
    spacing: { before: 320, after: 160 },
  });
}
function h3(text) {
  return new Paragraph({
    heading: HeadingLevel.HEADING_3,
    children: [new TextRun({ text, font: "Arial", size: 24, bold: true, color: BLUE_DARK })],
    spacing: { before: 240, after: 120 },
  });
}
function para(text, opts = {}) {
  return new Paragraph({
    children: [new TextRun({ text, font: "Arial", size: 22, color: "222222", ...opts })],
    spacing: { before: 80, after: 80 },
  });
}
function bold(text, color = "1F3864") {
  return new TextRun({ text, font: "Arial", size: 22, bold: true, color });
}
function normal(text) {
  return new TextRun({ text, font: "Arial", size: 22, color: "222222" });
}
function mixedPara(runs, spacing = { before: 80, after: 80 }) {
  return new Paragraph({ children: runs, spacing });
}
function bullet(text, level = 0, opts = {}) {
  return new Paragraph({
    numbering: { reference: "bullets", level },
    children: [new TextRun({ text, font: "Arial", size: 22, color: "222222", ...opts })],
    spacing: { before: 60, after: 60 },
  });
}
function numbered(text, level = 0, opts = {}) {
  return new Paragraph({
    numbering: { reference: "numbers", level },
    children: [new TextRun({ text, font: "Arial", size: 22, color: "222222", ...opts })],
    spacing: { before: 60, after: 60 },
  });
}
function divider(color = BLUE_MID) {
  return new Paragraph({
    children: [new TextRun("")],
    border: { bottom: { style: BorderStyle.SINGLE, size: 6, color, space: 1 } },
    spacing: { before: 160, after: 160 },
  });
}
function spacer(before = 120, after = 120) {
  return new Paragraph({ children: [new TextRun("")], spacing: { before, after } });
}
function pageBreak() {
  return new Paragraph({ children: [new PageBreak()] });
}

function cell(text, opts = {}) {
  const {
    fill = "FFFFFF", bold: isBold = false, color = "222222",
    colSpan, width = 2000, align = AlignmentType.LEFT, size = 20,
  } = opts;
  return new TableCell({
    borders: BORDERS,
    width: { size: width, type: WidthType.DXA },
    shading: { fill, type: ShadingType.CLEAR },
    margins: { top: 80, bottom: 80, left: 120, right: 120 },
    columnSpan: colSpan,
    verticalAlign: VerticalAlign.CENTER,
    children: [new Paragraph({
      alignment: align,
      children: [new TextRun({ text, font: "Arial", size, bold: isBold, color })],
    })],
  });
}

function headerCell(text, fill = BLUE_DARK, color = "FFFFFF", width = 2000) {
  return cell(text, { fill, bold: true, color, width });
}

function phaseBox(label, color, fill) {
  return new Table({
    width: { size: 9360, type: WidthType.DXA },
    columnWidths: [9360],
    rows: [new TableRow({ children: [
      new TableCell({
        borders: NO_BORDERS,
        shading: { fill, type: ShadingType.CLEAR },
        margins: { top: 120, bottom: 120, left: 240, right: 240 },
        children: [new Paragraph({ children: [
          new TextRun({ text: label, font: "Arial", size: 28, bold: true, color }),
        ]})],
      }),
    ]})],
  });
}

// ── DOCUMENT ─────────────────────────────────────────────────────────────────
const doc = new Document({
  numbering: {
    config: [
      { reference: "bullets", levels: [{
        level: 0, format: LevelFormat.BULLET, text: "•",
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 720, hanging: 360 } } },
      }, {
        level: 1, format: LevelFormat.BULLET, text: "◦",
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 1080, hanging: 360 } } },
      }]},
      { reference: "numbers", levels: [{
        level: 0, format: LevelFormat.DECIMAL, text: "%1.",
        alignment: AlignmentType.LEFT,
        style: { paragraph: { indent: { left: 720, hanging: 360 } } },
      }]},
    ],
  },
  styles: {
    default: { document: { run: { font: "Arial", size: 22 } } },
    paragraphStyles: [
      { id: "Heading1", name: "Heading 1", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 36, bold: true, font: "Arial", color: BLUE_DARK },
        paragraph: { spacing: { before: 400, after: 200 }, outlineLevel: 0 } },
      { id: "Heading2", name: "Heading 2", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 28, bold: true, font: "Arial", color: BLUE_MID },
        paragraph: { spacing: { before: 320, after: 160 }, outlineLevel: 1 } },
      { id: "Heading3", name: "Heading 3", basedOn: "Normal", next: "Normal", quickFormat: true,
        run: { size: 24, bold: true, font: "Arial", color: BLUE_DARK },
        paragraph: { spacing: { before: 240, after: 120 }, outlineLevel: 2 } },
    ],
  },
  sections: [{
    properties: {
      page: {
        size: { width: 12240, height: 15840 },
        margin: { top: 1080, right: 1080, bottom: 1080, left: 1080 },
      },
    },
    headers: {
      default: new Header({ children: [
        new Paragraph({
          children: [
            new TextRun({ text: "CS AI Engine — Startup Product & Engineering Roadmap", font: "Arial", size: 18, color: "888888" }),
            new TextRun({ text: "\t", font: "Arial", size: 18 }),
            new TextRun({ text: "v1.0 · April 2026", font: "Arial", size: 18, color: "888888" }),
          ],
          tabStops: [{ type: "right", position: 9360 }],
          border: { bottom: { style: BorderStyle.SINGLE, size: 4, color: BLUE_MID, space: 1 } },
        }),
      ]}),
    },
    footers: {
      default: new Footer({ children: [
        new Paragraph({
          children: [
            new TextRun({ text: "CONFIDENTIAL — Internal Use Only", font: "Arial", size: 16, color: "AAAAAA" }),
            new TextRun({ text: "\t", font: "Arial", size: 16 }),
            new TextRun({ children: ["Page ", PageNumber.CURRENT, " of ", PageNumber.TOTAL_PAGES], font: "Arial", size: 16, color: "888888" }),
          ],
          tabStops: [{ type: "right", position: 9360 }],
          border: { top: { style: BorderStyle.SINGLE, size: 4, color: BLUE_MID, space: 1 } },
        }),
      ]}),
    },
    children: [

      // ══════════════════════════════════════════
      // COVER
      // ══════════════════════════════════════════
      spacer(400, 200),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: "CS AI ENGINE", font: "Arial", size: 56, bold: true, color: BLUE_DARK })],
        spacing: { before: 400, after: 80 },
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: "Startup Product & Engineering Roadmap", font: "Arial", size: 36, color: BLUE_MID })],
        spacing: { before: 80, after: 80 },
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: "From Prototype to Production-Grade Platform", font: "Arial", size: 26, color: "666666", italics: true })],
        spacing: { before: 80, after: 400 },
      }),
      divider(BLUE_MID),
      spacer(120, 80),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: "Based on: Deep Architecture Research · OpenAI & Anthropic Agent Guides · McKinsey AI Adoption · CNIL Compliance", font: "Arial", size: 20, color: "888888", italics: true })],
        spacing: { before: 80, after: 80 },
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: "April 2026 — CONFIDENTIAL", font: "Arial", size: 20, bold: true, color: BLUE_DARK })],
        spacing: { before: 80, after: 400 },
      }),
      pageBreak(),

      // ══════════════════════════════════════════
      // TABLE OF CONTENTS
      // ══════════════════════════════════════════
      h1("Table of Contents"),
      new TableOfContents("Table of Contents", { hyperlink: true, headingStyleRange: "1-3" }),
      pageBreak(),

      // ══════════════════════════════════════════
      // 1. EXECUTIVE SUMMARY
      // ══════════════════════════════════════════
      h1("1. Executive Summary"),
      divider(),
      para("This document is the definitive product and engineering roadmap for the CS AI Engine as it transitions from a working prototype to a serious startup-grade platform. It is grounded in deep research synthesizing recommendations from OpenAI, Anthropic, McKinsey, NVIDIA, CNIL, OWASP, and NIST, as well as foundational AI agent papers (ReAct, Toolformer, Self-Refine, Reflexion)."),
      spacer(60, 60),
      para("The central finding is blunt: the real competitive moat for a customer service AI product is not a cleverer prompt — it is a reliable workflow, robust connectors, proprietary evaluation datasets, and a control layer that transforms a variable LLM into a deterministic system at critical decision points."),
      spacer(60, 60),
      para("78% of organizations now use AI in at least one function, yet more than 80% report no tangible EBIT impact at scale. The bottleneck is always the same: data quality, governance, interoperability, and inability to prove ROI. This is the exact gap our product must close — not by adding more agents, but by building the infrastructure that makes every agent trustworthy, auditable, and measurable."),
      spacer(80, 80),

      // summary table
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [2400, 6960],
        rows: [
          new TableRow({ children: [headerCell("Dimension", BLUE_DARK, "FFFFFF", 2400), headerCell("Our Answer", BLUE_DARK, "FFFFFF", 6960)] }),
          new TableRow({ children: [cell("Core product", { fill: BLUE_PALE, bold: true, width: 2400 }), cell("Customer decision orchestration layer — not just a chat agent", { width: 6960 })] }),
          new TableRow({ children: [cell("Architecture", { fill: GRAY_FILL, bold: true, width: 2400 }), cell("3 planes: Control (state + policies), Truth (facts + validation), Experience (drafting + tone + memory)", { fill: GRAY_FILL, width: 6960 })] }),
          new TableRow({ children: [cell("Wedge", { fill: BLUE_PALE, bold: true, width: 2400 }), cell("One high-value workflow mastered end-to-end, then expanded — not a feature sprawl", { width: 6960 })] }),
          new TableRow({ children: [cell("Moat", { fill: GRAY_FILL, bold: true, width: 2400 }), cell("Proprietary eval datasets, connector reliability, policy engine, audit trail", { fill: GRAY_FILL, width: 6960 })] }),
          new TableRow({ children: [cell("Compliance", { fill: BLUE_PALE, bold: true, width: 2400 }), cell("CNIL-ready from day one: PII redaction, structured logging, human oversight, justified retention", { width: 6960 })] }),
          new TableRow({ children: [cell("Timeline", { fill: GRAY_FILL, bold: true, width: 2400 }), cell("4 phases over 28 weeks: Foundation → Reliability → Intelligence → Scale", { fill: GRAY_FILL, width: 6960 })] }),
        ],
      }),
      pageBreak(),

      // ══════════════════════════════════════════
      // 2. STRATEGIC CONTEXT
      // ══════════════════════════════════════════
      h1("2. Strategic Context & Market Position"),
      divider(),
      h2("2.1 The Market Signal"),
      para("The data is clear: the market for agentic customer service AI is large and accelerating, but the conversion from experimentation to real value is extremely low. Nearly two thirds of enterprises have piloted AI agents; fewer than 10% have reached tangible value at scale. 8 in 10 cite data limitations as the primary blocker. 30% of respondents in NVIDIA's 2026 survey lack clarity on ROI."),
      spacer(60, 60),
      para("This is not a technology gap — it is an execution and trust gap. The companies that will win are those that can prove the system works, prove it is safe, and prove it is worth the investment. That proof lives in the product itself, not in sales decks."),
      spacer(80, 80),
      h2("2.2 What the Research Tells Us to Build"),

      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [4200, 5160],
        rows: [
          new TableRow({ children: [headerCell("SOTA Finding", BLUE_DARK, "FFFFFF", 4200), headerCell("Product Implication for CS AI Engine", BLUE_DARK, "FFFFFF", 5160)] }),
          new TableRow({ children: [cell("Start simple: mono-agent + tools before multi-agent", { fill: BLUE_PALE, width: 4200 }), cell("One central orchestrator; each new agent must justify a measurable gain", { width: 5160 })] }),
          new TableRow({ children: [cell("Context is a finite, degradable resource", { fill: GRAY_FILL, width: 4200 }), cell("Bounded memory, scoped per ticket/client, aggressive input cleaning, fact registry", { fill: GRAY_FILL, width: 5160 })] }),
          new TableRow({ children: [cell("Agents die at scale on data quality", { fill: BLUE_PALE, width: 4200 }), cell("Fact registry with provenance, TTL, validation — no hallucination without a verified fact", { width: 5160 })] }),
          new TableRow({ children: [cell("Tools define overall quality", { fill: GRAY_FILL, width: 4200 }), cell("Narrow APIs, explicit names, token-efficient responses, minimal permissions", { fill: GRAY_FILL, width: 5160 })] }),
          new TableRow({ children: [cell("Enterprises pay for governance", { fill: BLUE_PALE, width: 4200 }), cell("Policy engine, audit trail, human approval on sensitive actions, controlled retention", { width: 5160 })] }),
          new TableRow({ children: [cell("Real gains come from workflow integration", { fill: GRAY_FILL, width: 4200 }), cell("ERP + CRM + Email connectors are not optional — they are the product", { fill: GRAY_FILL, width: 5160 })] }),
        ],
      }),
      spacer(120, 120),
      h2("2.3 Our Competitive Positioning"),
      para("The defensible position for a startup in this space is not to out-model OpenAI or Anthropic. It is to out-operate them in the narrow domain of B2B customer service. That means:"),
      bullet("Deep workflow knowledge baked into the policy engine — rules a generic LLM cannot know"),
      bullet("Connector reliability no horizontal platform bothers with (ERP-specific retries, schema validation, deduplication)"),
      bullet("A proprietary eval corpus that gets better every week as real tickets flow through the system"),
      bullet("An audit trail that satisfies a CNIL audit, a SOC 2 reviewer, and an enterprise procurement officer"),
      pageBreak(),

      // ══════════════════════════════════════════
      // 3. ARCHITECTURE
      // ══════════════════════════════════════════
      h1("3. Target Architecture"),
      divider(),
      h2("3.1 The Three-Plane Model"),
      para("The architecture must be structured around three distinct planes. This separation is the foundation that makes the system controllable, auditable, and scalable."),
      spacer(80, 80),

      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [2000, 3200, 4160],
        rows: [
          new TableRow({ children: [headerCell("Plane", BLUE_DARK, "FFFFFF", 2000), headerCell("Responsibility", BLUE_DARK, "FFFFFF", 3200), headerCell("Key Components", BLUE_DARK, "FFFFFF", 4160)] }),
          new TableRow({ children: [
            cell("CONTROL PLANE", { fill: RED_FILL, bold: true, color: RED, width: 2000 }),
            cell("State machine, policies, decisions, routing", { fill: RED_FILL, width: 3200 }),
            cell("TicketState FSM · PolicyEngine · DecisionEngine · IdempotencyGuard", { fill: RED_FILL, width: 4160 }),
          ]}),
          new TableRow({ children: [
            cell("TRUTH PLANE", { fill: YELLOW_FILL, bold: true, color: ORANGE, width: 2000 }),
            cell("Verified facts, provenance, validation, anti-hallucination", { fill: YELLOW_FILL, width: 3200 }),
            cell("FactRegistry · ValidatorAgent · ClaimChecker · ConnectorResults", { fill: YELLOW_FILL, width: 4160 }),
          ]}),
          new TableRow({ children: [
            cell("EXPERIENCE PLANE", { fill: GREEN_FILL, bold: true, color: GREEN, width: 2000 }),
            cell("Drafting, tone, memory, role-aware behaviour", { fill: GREEN_FILL, width: 3200 }),
            cell("ResponseAgent · QAAgent · SelfCritiqueAgent · ScopedMemory · FallbackTemplates", { fill: GREEN_FILL, width: 4160 }),
          ]}),
        ],
      }),
      spacer(120, 120),
      h2("3.2 Pipeline Flow"),
      para("Every message follows a deterministic path through eight stages. No stage can be skipped. Each stage emits a trace."),
      spacer(80, 80),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [480, 2400, 3480, 2800],
        rows: [
          new TableRow({ children: [
            headerCell("#", BLUE_DARK, "FFFFFF", 480),
            headerCell("Stage", BLUE_DARK, "FFFFFF", 2400),
            headerCell("What it does", BLUE_DARK, "FFFFFF", 3480),
            headerCell("Output contract", BLUE_DARK, "FFFFFF", 2800),
          ]}),
          new TableRow({ children: [cell("1", { fill: GRAY_FILL, width: 480, align: AlignmentType.CENTER }), cell("Input Cleaning", { fill: GRAY_FILL, width: 2400, bold: true }), cell("Strip quoted chains, HTML, signatures, injections, noise senders", { fill: GRAY_FILL, width: 3480 }), cell("CleanMessage + SanitizationReport", { fill: GRAY_FILL, width: 2800 })] }),
          new TableRow({ children: [cell("2", { width: 480, align: AlignmentType.CENTER }), cell("Triage", { width: 2400, bold: true }), cell("Classify intent, emotion, language, risk flags, missing fields, confidence scores", { width: 3480 }), cell("TriageResult (strict Pydantic)", { width: 2800 })] }),
          new TableRow({ children: [cell("3", { fill: GRAY_FILL, width: 480, align: AlignmentType.CENTER }), cell("Fact Builder", { fill: GRAY_FILL, width: 2400, bold: true }), cell("Query ERP, CRM, KB — build verified fact objects with source + TTL", { fill: GRAY_FILL, width: 3480 }), cell("list[Fact] in FactRegistry", { fill: GRAY_FILL, width: 2800 })] }),
          new TableRow({ children: [cell("4", { width: 480, align: AlignmentType.CENTER }), cell("Response Agent", { width: 2400, bold: true }), cell("Draft reply using only verified facts; reference prompt version", { width: 3480 }), cell("DraftResponse with facts_used refs", { width: 2800 })] }),
          new TableRow({ children: [cell("5", { fill: GRAY_FILL, width: 480, align: AlignmentType.CENTER }), cell("Self-Critique", { fill: GRAY_FILL, width: 2400, bold: true }), cell("Agent reviews its own draft for accuracy, tone, completeness", { fill: GRAY_FILL, width: 3480 }), cell("SelfCritiqueResult", { fill: GRAY_FILL, width: 2800 })] }),
          new TableRow({ children: [cell("6", { width: 480, align: AlignmentType.CENTER }), cell("Validator + Policy", { width: 2400, bold: true }), cell("Check every claim against FactRegistry; evaluate policy rules", { width: 3480 }), cell("ValidationResult + PolicyDecision", { width: 2800 })] }),
          new TableRow({ children: [cell("7", { fill: GRAY_FILL, width: 480, align: AlignmentType.CENTER }), cell("QA Rewriter", { fill: GRAY_FILL, width: 2400, bold: true }), cell("Fix tone, language, length per role/segment/SLA tier", { fill: GRAY_FILL, width: 3480 }), cell("Final draft string", { fill: GRAY_FILL, width: 2800 })] }),
          new TableRow({ children: [cell("8", { width: 480, align: AlignmentType.CENTER }), cell("Decision Engine", { width: 2400, bold: true }), cell("Route: send / human review / block / escalate — deterministic rules only", { width: 3480 }), cell("DecisionResult: action + reason + human_required", { width: 2800 })] }),
        ],
      }),
      spacer(120, 120),
      h2("3.3 File Structure (Target State)"),
      para("The codebase must be reorganised around this structure. The current flat layout mixes concerns that must be separated for the system to scale."),
      spacer(80, 80),
      new Paragraph({
        children: [new TextRun({
          text: [
            "src/",
            "  core/        → config, logging, tracing, policies, state_machine, ids",
            "  schemas/     → core, messages, facts, connectors, decisions",
            "  agents/      → triage, fact_builder, responder, self_critique,",
            "                  validator, qa, decision",
            "  connectors/  → base, email, erp, crm, kb, attachments",
            "  storage/     → repo, audit, prompt_registry",
            "  orchestrator/→ service (the single entry point), tasks",
            "  templates/   → fallback/ (Jinja2, never LLM in red zones)",
            "  evals/       → dataset/, simulator, graders, reports",
            "tests/",
            "  unit/        → state machine, policies, validators, dedup",
            "  integration/ → full pipeline on nominal cases",
            "  contract/    → frozen ERP/CRM/email mocks",
            "  synthetic/   → adversarial, multilingual, conflict, injection",
            "  regressions/ → frozen eval dataset + CI gate",
          ].join("\n"),
          font: "Courier New", size: 18, color: "333333",
        })],
        spacing: { before: 80, after: 80 },
        shading: { fill: GRAY_FILL, type: ShadingType.CLEAR },
      }),
      pageBreak(),

      // ══════════════════════════════════════════
      // 4. ROADMAP PHASES
      // ══════════════════════════════════════════
      h1("4. Roadmap — Four Phases"),
      divider(),
      para("The roadmap is structured in four sequential phases. Each phase has a clear entry condition, a clear exit condition, and measurable success criteria. No phase starts until the previous one passes its exit gate."),
      spacer(120, 120),

      // ─── PHASE 0 ───
      phaseBox("PHASE 0 — FOUNDATION  (Weeks 1–4)  \"Make It Unbreakable\"", RED, RED_FILL),
      spacer(80, 80),
      mixedPara([bold("Goal: "), normal("The system never crashes, never halts mysteriously, never sends incorrect information. Every action is traceable. The foundation for everything else.")]),
      spacer(60, 60),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [3200, 3280, 2880],
        rows: [
          new TableRow({ children: [headerCell("Deliverable", RED, "FFFFFF", 3200), headerCell("Technical spec", RED, "FFFFFF", 3280), headerCell("Done when…", RED, "FFFFFF", 2880)] }),
          new TableRow({ children: [cell("State Machine", { fill: RED_FILL, bold: true, width: 3200 }), cell("TicketState Enum + transition matrix + InvalidTransitionError + idempotent retry_count", { fill: RED_FILL, width: 3280 }), cell("Parameterised tests cover ALL valid and invalid transitions", { fill: RED_FILL, width: 2880 })] }),
          new TableRow({ children: [cell("Typed Schemas", { bold: true, width: 3200 }), cell("Pydantic strict models at every agent boundary — TriageResult, Fact, DraftResponse, ValidationResult, DecisionResult", { width: 3280 }), cell("Zero dict passing between agents; ValidationError stops execution", { width: 2880 })] }),
          new TableRow({ children: [cell("Fact Registry", { fill: RED_FILL, bold: true, width: 3200 }), cell("Fact(key, value, source_ref, verified, observed_at, ttl_s, sensitivity); ValidatorAgent checks every claim against registry", { fill: RED_FILL, width: 3280 }), cell("Unverified claim = unsupported_claim event + block decision", { fill: RED_FILL, width: 2880 })] }),
          new TableRow({ children: [cell("Connector Resilience", { bold: true, width: 3200 }), cell("ConnectorResult[T] envelope, ConnectorError(kind: retryable|fatal|auth|rate_limit), exponential backoff + jitter + circuit breaker via Tenacity", { width: 3280 }), cell("Connector failure never crashes the orchestrator; all errors are classified and logged", { width: 2880 })] }),
          new TableRow({ children: [cell("Policy Engine", { fill: RED_FILL, bold: true, width: 3200 }), cell("Code-first rules (Python, not prompt), deny-by-default, human approval required for: sensitive writes, angry + low confidence, unverified date promises", { fill: RED_FILL, width: 3280 }), cell("All policy violations produce SECURITY log entry + block action", { fill: RED_FILL, width: 2880 })] }),
          new TableRow({ children: [cell("Idempotency", { bold: true, width: 3200 }), cell("IdempotencyKey per message/thread/action; hash-based dedup on inbound; no write without key; DuplicateSuppressed event", { width: 3280 }), cell("Sending same email twice produces one ticket and one reply", { width: 2880 })] }),
          new TableRow({ children: [cell("Trace Logging", { fill: RED_FILL, bold: true, width: 3200 }), cell("StepTrace per stage: run_id, ticket_id, step_name, latency_ms, input/output tokens, model, prompt_version, error_code. No raw PII in logs.", { fill: RED_FILL, width: 3280 }), cell("Every ticket produces a complete, queryable trace from inbound to decision", { fill: RED_FILL, width: 2880 })] }),
        ],
      }),
      spacer(80, 80),
      mixedPara([bold("Phase 0 Exit Gate: "), normal("All unit tests pass. All P0 schemas validated. Zero unclassified exceptions in a 100-ticket smoke test. State machine has 100% transition coverage.")]),
      spacer(120, 120),

      // ─── PHASE 1 ───
      phaseBox("PHASE 1 — RELIABILITY  (Weeks 5–10)  \"Make It Production-Worthy\"", ORANGE, ORANGE_FILL),
      spacer(80, 80),
      mixedPara([bold("Goal: "), normal("The system is safe to show to a first paying customer. It handles messy real-world input, has a CI gate, and every regression is caught before it ships.")]),
      spacer(60, 60),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [3200, 3280, 2880],
        rows: [
          new TableRow({ children: [headerCell("Deliverable", ORANGE, "FFFFFF", 3200), headerCell("Technical spec", ORANGE, "FFFFFF", 3280), headerCell("Done when…", ORANGE, "FFFFFF", 2880)] }),
          new TableRow({ children: [cell("Prompt Registry", { fill: ORANGE_FILL, bold: true, width: 3200 }), cell("PromptSpec: prompt_id, semver, checksum, variables, changelog. No inline prompts in production. Every LLM call references a versioned spec.", { fill: ORANGE_FILL, width: 3280 }), cell("Git blame on any prompt regression — traceable to exact version + PR", { fill: ORANGE_FILL, width: 2880 })] }),
          new TableRow({ children: [cell("Eval Harness + CI Gate", { bold: true, width: 3200 }), cell("Frozen dataset of 50+ cases (nominal, ambiguous, adversarial, ERP conflict). Graders score intent accuracy, claim support, decision correctness. Blocks merge if score < baseline.", { width: 3280 }), cell("CI fails on regression. Eval report as build artefact on every PR.", { width: 2880 })] }),
          new TableRow({ children: [cell("Adversarial Input Cleaning", { fill: ORANGE_FILL, bold: true, width: 3200 }), cell("Strip: quoted reply chains, HTML, signatures, prompt injections, noise senders (mailer-daemon, noreply, postmaster), Re: Re: Re: loops", { fill: ORANGE_FILL, width: 3280 }), cell("Injection attempts in email body never reach the LLM. Noise emails never become tickets.", { fill: ORANGE_FILL, width: 2880 })] }),
          new TableRow({ children: [cell("Fallback Templates", { bold: true, width: 3200 }), cell("Jinja2 templates per case: missing_info, system_down, high_risk, ambiguous. Applied by decision engine when LLM output is blocked or confidence is below floor.", { width: 3280 }), cell("No LLM-free ticket goes unanswered. Customer always gets a coherent response.", { width: 2880 })] }),
          new TableRow({ children: [cell("OpenTelemetry Integration", { fill: ORANGE_FILL, bold: true, width: 3200 }), cell("Spans + metrics + logs correlated by run_id. Exported to chosen backend (Grafana, Datadog, etc.). Dashboard: p95 latency, error rates, token costs, review rate.", { fill: ORANGE_FILL, width: 3280 }), cell("Operations team can diagnose any issue from the dashboard without reading code.", { fill: ORANGE_FILL, width: 2880 })] }),
          new TableRow({ children: [cell("Startup Config Validation", { bold: true, width: 3200 }), cell("ConfigValidator checks all required fields before app launches. Clear errors with fix instructions. Warnings for optional fields.", { width: 3280 }), cell("Onboarding a new company never crashes mid-session due to missing config.", { width: 2880 })] }),
        ],
      }),
      spacer(80, 80),
      mixedPara([bold("Phase 1 Exit Gate: "), normal("Eval harness runs in CI. Adversarial test suite passes. First customer demo environment is stable for 48h without manual intervention.")]),
      spacer(120, 120),

      // ─── PHASE 2 ───
      phaseBox("PHASE 2 — INTELLIGENCE  (Weeks 11–18)  \"Make It Smart\"", "375623", GREEN_FILL),
      spacer(80, 80),
      mixedPara([bold("Goal: "), normal("The system handles real B2B complexity: attachments, memory, multiple languages, multiple customer profiles. It learns from its own history.")]),
      spacer(60, 60),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [3200, 3280, 2880],
        rows: [
          new TableRow({ children: [headerCell("Deliverable", "375623", "FFFFFF", 3200), headerCell("Technical spec", "375623", "FFFFFF", 3280), headerCell("Done when…", "375623", "FFFFFF", 2880)] }),
          new TableRow({ children: [cell("Scoped Memory", { fill: GREEN_FILL, bold: true, width: 3200 }), cell("MemoryItem(scope: ticket|client|account, ttl, size_limit, checksum). PII redacted before persistence. No global unfiltered memory.", { fill: GREEN_FILL, width: 3280 }), cell("Agent recalls previous interactions in same thread. No cross-customer data bleed.", { fill: GREEN_FILL, width: 2880 })] }),
          new TableRow({ children: [cell("Attachment Module", { bold: true, width: 3200 }), cell("Classify doc type, extract structured fields with confidence per field. Isolated from main text pipeline. Antivirus hook if available. Extracted fields fed into FactRegistry.", { width: 3280 }), cell("Invoice PDF produces verified Fact objects. Extraction failure does not block ticket.", { width: 2880 })] }),
          new TableRow({ children: [cell("Role-Aware Behaviour", { fill: GREEN_FILL, bold: true, width: 3200 }), cell("ResponsePolicy per role + customer segment + language + severity. Tone rules enforced in QA agent and policy engine, not only in the prompt.", { fill: GREEN_FILL, width: 3280 }), cell("Tone audit on 20 real tickets shows correct register for segment in 90%+ cases.", { fill: GREEN_FILL, width: 2880 })] }),
          new TableRow({ children: [cell("KB Usage Tracking", { bold: true, width: 3200 }), cell("Log every KB entry retrieved. Mark as helpful on draft approval. Flag unused entries (30 days). Flag low-approval entries (<40%) for review.", { width: 3280 }), cell("Analytics dashboard shows KB health. Dead entries identified within 30 days.", { width: 2880 })] }),
          new TableRow({ children: [cell("Lesson Effectiveness Tracking", { fill: GREEN_FILL, bold: true, width: 3200 }), cell("Track whether lessons injected into prompts actually improve draft quality. A/B at prompt version level.", { fill: GREEN_FILL, width: 3280 }), cell("Each lesson has a measured effect score. Ineffective lessons are retired automatically.", { fill: GREEN_FILL, width: 2880 })] }),
          new TableRow({ children: [cell("Pipeline Timing Dashboards", { bold: true, width: 3200 }), cell("Per-stage latency visible in UI. SLO breach alerts. Cost per ticket per account.", { width: 3280 }), cell("Operations can identify the bottleneck stage for any slow ticket in under 2 minutes.", { width: 2880 })] }),
        ],
      }),
      spacer(80, 80),
      mixedPara([bold("Phase 2 Exit Gate: "), normal("3 real B2B customers in production. Attachment handling live. KB usage dashboard showing data. p95 latency under 3s end-to-end.")]),
      spacer(120, 120),

      // ─── PHASE 3 ───
      phaseBox("PHASE 3 — SCALE  (Weeks 19–28)  \"Make It a Platform\"", BLUE_DARK, BLUE_PALE),
      spacer(80, 80),
      mixedPara([bold("Goal: "), normal("The system is a platform: multi-tenant, self-service onboarding, connector marketplace, enterprise audit capabilities. Ready for Series A narrative.")]),
      spacer(60, 60),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [3200, 3280, 2880],
        rows: [
          new TableRow({ children: [headerCell("Deliverable", BLUE_DARK, "FFFFFF", 3200), headerCell("Technical spec", BLUE_DARK, "FFFFFF", 3280), headerCell("Done when…", BLUE_DARK, "FFFFFF", 2880)] }),
          new TableRow({ children: [cell("Multi-Tenant Account Isolation", { fill: BLUE_PALE, bold: true, width: 3200 }), cell("Complete data isolation per account: separate fact registries, memory scopes, policy rule sets, prompt versions, audit trails.", { fill: BLUE_PALE, width: 3280 }), cell("Security review confirms zero cross-account data access in penetration test.", { fill: BLUE_PALE, width: 2880 })] }),
          new TableRow({ children: [cell("Self-Service Onboarding", { bold: true, width: 3200 }), cell("Guided config wizard + ConfigValidator + connector health check + template playground. New account live in under 1 hour.", { width: 3280 }), cell("5 new accounts onboarded by a non-engineer in under 1 hour each.", { width: 2880 })] }),
          new TableRow({ children: [cell("Connector Marketplace", { fill: BLUE_PALE, bold: true, width: 3200 }), cell("Standardised ConnectorResult[T] interface allows third-party connectors. SDK + docs + sandbox.", { fill: BLUE_PALE, width: 3280 }), cell("2 partner connectors built by external developers using the SDK.", { fill: BLUE_PALE, width: 2880 })] }),
          new TableRow({ children: [cell("Enterprise Audit Export", { bold: true, width: 3200 }), cell("Full AuditEvent export per account, date range, event type. CNIL-compliant retention policy enforced automatically.", { width: 3280 }), cell("Enterprise customer passes internal compliance review using our audit export.", { width: 2880 })] }),
          new TableRow({ children: [cell("Cost Optimisation Layer", { fill: BLUE_PALE, bold: true, width: 3200 }), cell("Route simple/high-confidence tickets to smaller/cheaper models. Complex/low-confidence to premium model. Cost vs. quality tradeoff governed by account config.", { fill: BLUE_PALE, width: 3280 }), cell("Token cost per ticket reduced by 30%+ vs Phase 0 baseline with no quality regression.", { fill: BLUE_PALE, width: 2880 })] }),
          new TableRow({ children: [cell("Synthetic Data Generator", { bold: true, width: 3200 }), cell("Generate eval cases from real tickets (PII stripped). Auto-grow dataset. Keeps CI gate relevant as product evolves.", { width: 3280 }), cell("Eval dataset grows automatically. No manual curation required for >80% of new cases.", { width: 2880 })] }),
        ],
      }),
      spacer(80, 80),
      mixedPara([bold("Phase 3 Exit Gate: "), normal("10+ active accounts. Series A deck can cite measurable EBIT impact per customer. SOC 2 / CNIL audit passed or in progress.")]),
      pageBreak(),

      // ══════════════════════════════════════════
      // 5. PRIORITY MATRIX
      // ══════════════════════════════════════════
      h1("5. Full Priority Matrix"),
      divider(),
      para("Every work item classified by priority (P0 = blocking, P1 = important, P2 = enhancement) and mapped to the phase in which it is completed."),
      spacer(80, 80),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [600, 2600, 2200, 1560, 1000, 1400],
        rows: [
          new TableRow({ children: [
            headerCell("Pri", BLUE_DARK, "FFFFFF", 600),
            headerCell("Item", BLUE_DARK, "FFFFFF", 2600),
            headerCell("Why it matters", BLUE_DARK, "FFFFFF", 2200),
            headerCell("Phase", BLUE_DARK, "FFFFFF", 1560),
            headerCell("Effort", BLUE_DARK, "FFFFFF", 1000),
            headerCell("Impact", BLUE_DARK, "FFFFFF", 1400),
          ]}),
          // P0
          ...[
            ["P0", "State Machine", "Prevents step-skipping; makes resumption deterministic", "Phase 0", "M", "Critical"],
            ["P0", "Typed Pydantic Schemas", "Eliminates shape bugs between agents and connectors", "Phase 0", "M", "Critical"],
            ["P0", "Fact Registry", "Strongly reduces hallucinations", "Phase 0", "M", "Critical"],
            ["P0", "Connector Resilience", "Upstream failures must not crash the engine", "Phase 0", "M", "Critical"],
            ["P0", "Policy Engine (code-first)", "Business rules must not depend on prompts", "Phase 0", "M", "Critical"],
            ["P0", "Confidence Decomposition", "One global score hides real weaknesses", "Phase 0", "S", "Critical"],
            ["P0", "Idempotency", "Prevents duplicate tickets, replies, escalations", "Phase 0", "M", "Critical"],
            ["P0", "Trace Logging (structured)", "Bugs and regressions must be diagnosable", "Phase 0", "M", "Critical"],
          ].map(([pri, item, why, phase, eff, imp]) => new TableRow({ children: [
            cell(pri, { fill: RED_FILL, bold: true, color: RED, width: 600, align: AlignmentType.CENTER }),
            cell(item, { fill: RED_FILL, bold: true, width: 2600 }),
            cell(why, { fill: RED_FILL, width: 2200 }),
            cell(phase, { fill: RED_FILL, width: 1560 }),
            cell(eff, { fill: RED_FILL, width: 1000, align: AlignmentType.CENTER }),
            cell(imp, { fill: RED_FILL, width: 1400, align: AlignmentType.CENTER }),
          ]})),
          // P1
          ...[
            ["P1", "Prompt Registry + Versioning", "Regressions must be attributable to a specific change", "Phase 1", "M", "High"],
            ["P1", "Eval Harness + CI Gate", "Without evals, every prompt change breaks something else", "Phase 1", "M", "High"],
            ["P1", "Adversarial Input Cleaning", "Email is an attack surface; injections must not reach LLM", "Phase 1", "S", "High"],
            ["P1", "Fallback Templates", "In doubt, a safe template beats a risky LLM response", "Phase 1", "S", "High"],
            ["P1", "OpenTelemetry Integration", "Ops team needs visibility without reading code", "Phase 1", "M", "High"],
            ["P1", "Config Startup Validation", "Setup errors must surface before a customer interaction", "Phase 1", "S", "High"],
            ["P1", "Scoped Memory", "Agent memory must be bounded, isolated, expirable", "Phase 2", "M", "Med/High"],
            ["P1", "Attachment Module", "B2B tickets live in PDFs and images", "Phase 2", "L", "High (B2B)"],
            ["P1", "KB Usage Tracking", "Unused or harmful KB entries degrade quality silently", "Phase 2", "M", "Medium"],
          ].map(([pri, item, why, phase, eff, imp]) => new TableRow({ children: [
            cell(pri, { fill: YELLOW_FILL, bold: true, color: ORANGE, width: 600, align: AlignmentType.CENTER }),
            cell(item, { fill: YELLOW_FILL, bold: true, width: 2600 }),
            cell(why, { fill: YELLOW_FILL, width: 2200 }),
            cell(phase, { fill: YELLOW_FILL, width: 1560 }),
            cell(eff, { fill: YELLOW_FILL, width: 1000, align: AlignmentType.CENTER }),
            cell(imp, { fill: YELLOW_FILL, width: 1400, align: AlignmentType.CENTER }),
          ]})),
          // P2
          ...[
            ["P2", "Role-Aware Behaviour", "Tone and style must adapt to customer segment", "Phase 2", "M", "Medium"],
            ["P2", "Lesson Effectiveness Tracking", "Learning system needs data before it can learn", "Phase 2", "M", "Medium"],
            ["P2", "Pipeline Timing UI", "Debugging aid and latency SLO visibility", "Phase 2", "S", "Low/Med"],
            ["P2", "Multi-Tenant Isolation", "Required before scaling to multiple enterprise accounts", "Phase 3", "L", "Strategic"],
            ["P2", "Cost Optimisation Layer", "Unit economics must improve as volume scales", "Phase 3", "M", "Medium"],
            ["P2", "Connector Marketplace SDK", "Third-party connectors multiply addressable market", "Phase 3", "L", "Strategic"],
          ].map(([pri, item, why, phase, eff, imp]) => new TableRow({ children: [
            cell(pri, { fill: GREEN_FILL, bold: true, color: GREEN, width: 600, align: AlignmentType.CENTER }),
            cell(item, { fill: GREEN_FILL, bold: true, width: 2600 }),
            cell(why, { fill: GREEN_FILL, width: 2200 }),
            cell(phase, { fill: GREEN_FILL, width: 1560 }),
            cell(eff, { fill: GREEN_FILL, width: 1000, align: AlignmentType.CENTER }),
            cell(imp, { fill: GREEN_FILL, width: 1400, align: AlignmentType.CENTER }),
          ]})),
        ],
      }),
      pageBreak(),

      // ══════════════════════════════════════════
      // 6. THE 7 IMMEDIATE ACTIONS
      // ══════════════════════════════════════════
      h1("6. The 7 Immediate Actions"),
      divider(),
      para("These are the seven tasks to implement right now, in this exact order. Each one unblocks the next. Do not start task 2 until task 1 is merged and tested."),
      spacer(80, 80),

      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [480, 2400, 3960, 2320],
        rows: [
          new TableRow({ children: [
            headerCell("#", BLUE_DARK, "FFFFFF", 480),
            headerCell("Task", BLUE_DARK, "FFFFFF", 2400),
            headerCell("Exactly what to build", BLUE_DARK, "FFFFFF", 3960),
            headerCell("Acceptance test", BLUE_DARK, "FFFFFF", 2320),
          ]}),
          new TableRow({ children: [
            cell("1", { fill: RED_FILL, bold: true, color: RED, width: 480, align: AlignmentType.CENTER }),
            cell("State Machine", { fill: RED_FILL, bold: true, width: 2400 }),
            cell("Create TicketState Enum, StateTransition model, transition matrix (dict of valid from→to pairs), InvalidTransitionError. Add retry_count and logical lock per ticket.", { fill: RED_FILL, width: 3960 }),
            cell("Parametrised pytest covers all 20+ transitions. Invalid transitions raise, not silently pass.", { fill: RED_FILL, width: 2320 }),
          ]}),
          new TableRow({ children: [
            cell("2", { bold: true, width: 480, align: AlignmentType.CENTER }),
            cell("Strict Pydantic Schemas", { bold: true, width: 2400 }),
            cell("Replace every dict passed between agents with strict Pydantic models. Start with TriageResult, then DraftResponse, ValidationResult, DecisionResult. ValidationError must stop execution.", { width: 3960 }),
            cell("Grep confirms zero raw dict() returns at agent boundaries. CI passes with strict mode.", { width: 2320 }),
          ]}),
          new TableRow({ children: [
            cell("3", { fill: RED_FILL, bold: true, color: RED, width: 480, align: AlignmentType.CENTER }),
            cell("Fact Registry", { fill: RED_FILL, bold: true, width: 2400 }),
            cell("Implement Fact(key, value, source_type, source_ref, verified, observed_at, ttl_s, sensitivity). FactRegistry stores facts by ticket_id. ValidatorAgent must compare every draft claim against the registry. Unverified claim = unsupported_claim flag + block.", { fill: RED_FILL, width: 3960 }),
            cell("Unit test: draft with unverified date claim produces block decision. Verified claim produces send.", { fill: RED_FILL, width: 2320 }),
          ]}),
          new TableRow({ children: [
            cell("4", { bold: true, width: 480, align: AlignmentType.CENTER }),
            cell("Unified Connector Interface", { bold: true, width: 2400 }),
            cell("All connectors return ConnectorResult[T]. All errors are ConnectorError(kind: retryable|fatal|auth|rate_limit|policy|timeout). Apply Tenacity retry with exponential backoff + jitter + stop_after_attempt(3). Circuit breaker on fatal.", { width: 3960 }),
            cell("Connector mock returning retryable error triggers 3 attempts then review. Fatal error triggers immediate review with no retry.", { width: 2320 }),
          ]}),
          new TableRow({ children: [
            cell("5", { fill: RED_FILL, bold: true, color: RED, width: 480, align: AlignmentType.CENTER }),
            cell("Policy Engine", { fill: RED_FILL, bold: true, width: 2400 }),
            cell("Code-first PolicyRule objects (not prompt text). Rules: (a) no promised delivery date without verified ERP fact, (b) no auto-send if emotion=angry AND confidence.final < 0.7, (c) no sensitive write without human approval. Deny-by-default.", { fill: RED_FILL, width: 3960 }),
            cell("Each rule has a dedicated unit test. Violation always produces SECURITY log + block. No rule is expressed only in a prompt.", { fill: RED_FILL, width: 2320 }),
          ]}),
          new TableRow({ children: [
            cell("6", { bold: true, width: 480, align: AlignmentType.CENTER }),
            cell("OpenTelemetry + Structured Logs", { bold: true, width: 2400 }),
            cell("Wire OTel spans per agent stage. Structured log fields: run_id, ticket_id, step_name, latency_ms, model, prompt_version, token_usage, decision, error_code. Zero raw PII in any log line.", { width: 3960 }),
            cell("Any ticket can be reconstructed from its trace without reading source code. PII audit confirms no email/name in logs.", { width: 2320 }),
          ]}),
          new TableRow({ children: [
            cell("7", { fill: RED_FILL, bold: true, color: RED, width: 480, align: AlignmentType.CENTER }),
            cell("Eval Harness + CI Gate", { fill: RED_FILL, bold: true, width: 2400 }),
            cell("Build evals/simulator.py and a frozen dataset of at least 50 cases: 15 nominal, 10 ambiguous/missing-data, 10 emotional/risk, 10 ERP-conflict, 5 adversarial-injection. Graders: intent accuracy, decision correctness, claim support rate. Block merge if score regresses beyond threshold.", { fill: RED_FILL, width: 3960 }),
            cell("Eval report generated on every PR. Intentionally broken prompt fails CI. Fixed prompt passes CI.", { fill: RED_FILL, width: 2320 }),
          ]}),
        ],
      }),
      pageBreak(),

      // ══════════════════════════════════════════
      // 7. ENGINEERING & CI STANDARDS
      // ══════════════════════════════════════════
      h1("7. Engineering Standards & CI Pipeline"),
      divider(),
      h2("7.1 CI Stages (in order)"),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [2800, 3280, 3280],
        rows: [
          new TableRow({ children: [headerCell("Stage", BLUE_DARK, "FFFFFF", 2800), headerCell("What runs", BLUE_DARK, "FFFFFF", 3280), headerCell("Blocking condition", BLUE_DARK, "FFFFFF", 3280)] }),
          new TableRow({ children: [cell("1. Lint + sanity", { fill: GRAY_FILL, bold: true, width: 2800 }), cell("ruff, mypy strict, import checks, config schema validation", { fill: GRAY_FILL, width: 3280 }), cell("Any import error or config invalid", { fill: GRAY_FILL, width: 3280 })] }),
          new TableRow({ children: [cell("2. Unit tests", { bold: true, width: 2800 }), cell("State machine, policies, validators, dedup, connector error classification", { width: 3280 }), cell("Any single failure", { width: 3280 })] }),
          new TableRow({ children: [cell("3. Contract tests", { fill: GRAY_FILL, bold: true, width: 2800 }), cell("Frozen ERP/CRM/email mocks — schema and error code contracts", { fill: GRAY_FILL, width: 3280 }), cell("Schema breakage or unexpected error code", { fill: GRAY_FILL, width: 3280 })] }),
          new TableRow({ children: [cell("4. Integration tests", { bold: true, width: 2800 }), cell("Full pipeline on nominal + edge cases", { width: 3280 }), cell("Unexpected decision result", { width: 3280 })] }),
          new TableRow({ children: [cell("5. Synthetic simulator", { fill: GRAY_FILL, bold: true, width: 2800 }), cell("Adversarial, multilingual, ERP conflict, attachment, injection", { fill: GRAY_FILL, width: 3280 }), cell("Hallucination or unjustified block/review rate increase", { fill: GRAY_FILL, width: 3280 })] }),
          new TableRow({ children: [cell("6. Prompt evals", { bold: true, width: 2800 }), cell("Frozen dataset + graders; nightly run is larger", { width: 3280 }), cell("Score < baseline minus threshold", { width: 3280 })] }),
          new TableRow({ children: [cell("7. Build + secrets scan", { fill: GRAY_FILL, bold: true, width: 2800 }), cell("Packaging, .env.example check, gitleaks scan", { fill: GRAY_FILL, width: 3280 }), cell("Secret detected in codebase or build broken", { fill: GRAY_FILL, width: 3280 })] }),
        ],
      }),
      spacer(120, 120),
      h2("7.2 Non-Negotiable Engineering Rules"),
      bullet("No raw dict passed between agents — Pydantic strict models only"),
      bullet("No prompt written inline — every LLM call references a versioned PromptSpec"),
      bullet("No secret in code — environment variables or secret manager only; never committed"),
      bullet("No write action without an idempotency key — DuplicateSuppressed is always safe"),
      bullet("No LLM response in a red zone — fallback templates for high_risk, system_down, ambiguous"),
      bullet("No PII in logs — redact before any log.write() or trace.set()"),
      bullet("No unclassified exception in production — every exception produces a classified error + action"),
      pageBreak(),

      // ══════════════════════════════════════════
      // 8. OBSERVABILITY & METRICS
      // ══════════════════════════════════════════
      h1("8. Observability & Business Metrics"),
      divider(),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [2800, 3200, 3360],
        rows: [
          new TableRow({ children: [headerCell("Metric", BLUE_DARK, "FFFFFF", 2800), headerCell("Why it matters", BLUE_DARK, "FFFFFF", 3200), headerCell("Initial SLO / Target", BLUE_DARK, "FFFFFF", 3360)] }),
          new TableRow({ children: [cell("triage_latency_ms", { fill: GRAY_FILL, bold: true, width: 2800 }), cell("Speed of understanding", { fill: GRAY_FILL, width: 3200 }), cell("p95 < 1200 ms", { fill: GRAY_FILL, width: 3360 })] }),
          new TableRow({ children: [cell("e2e_pipeline_latency_ms", { bold: true, width: 2800 }), cell("Customer-perceived responsiveness", { width: 3200 }), cell("p95 < 5000 ms (Phase 0) → < 3000 ms (Phase 2)", { width: 3360 })] }),
          new TableRow({ children: [cell("connector_error_rate", { fill: GRAY_FILL, bold: true, width: 2800 }), cell("Integration health per backend", { fill: GRAY_FILL, width: 3200 }), cell("< 1% per connector", { fill: GRAY_FILL, width: 3360 })] }),
          new TableRow({ children: [cell("schema_validation_fail_rate", { bold: true, width: 2800 }), cell("Shape bugs between agents", { width: 3200 }), cell("< 0.2%", { width: 3360 })] }),
          new TableRow({ children: [cell("unsupported_claim_rate", { fill: GRAY_FILL, bold: true, width: 2800 }), cell("Hallucination detection proxy", { fill: GRAY_FILL, width: 3200 }), cell("Downward trend every release", { fill: GRAY_FILL, width: 3360 })] }),
          new TableRow({ children: [cell("review_rate", { bold: true, width: 2800 }), cell("Engine calibration signal", { width: 3200 }), cell("Stable by ticket type; no unexplained spikes", { width: 3360 })] }),
          new TableRow({ children: [cell("escalation_rate", { fill: GRAY_FILL, bold: true, width: 2800 }), cell("Operational quality per account", { fill: GRAY_FILL, width: 3200 }), cell("Weekly review per account", { fill: GRAY_FILL, width: 3360 })] }),
          new TableRow({ children: [cell("fallback_rate", { bold: true, width: 2800 }), cell("True resilience under load/failure", { width: 3200 }), cell("No silent drift; alert if > 5% in 1h window", { width: 3360 })] }),
          new TableRow({ children: [cell("token_cost_per_ticket", { fill: GRAY_FILL, bold: true, width: 2800 }), cell("Unit economics visibility", { fill: GRAY_FILL, width: 3200 }), cell("Dashboard per account + per workflow type", { fill: GRAY_FILL, width: 3360 })] }),
          new TableRow({ children: [cell("prompt_regression_score", { bold: true, width: 2800 }), cell("Safety of LLM changes", { width: 3200 }), cell("Block merge on any regression beyond threshold", { width: 3360 })] }),
          new TableRow({ children: [cell("duplicate_suppression_rate", { fill: GRAY_FILL, bold: true, width: 2800 }), cell("Email ingestion hygiene", { fill: GRAY_FILL, width: 3200 }), cell("Measured; not targeted to zero", { fill: GRAY_FILL, width: 3360 })] }),
          new TableRow({ children: [cell("kb_approval_rate", { bold: true, width: 2800 }), cell("Knowledge base quality signal", { width: 3200 }), cell("Flag entries < 40% with >= 5 retrievals", { width: 3360 })] }),
        ],
      }),
      pageBreak(),

      // ══════════════════════════════════════════
      // 9. SECURITY & COMPLIANCE
      // ══════════════════════════════════════════
      h1("9. Security & Compliance Checklist"),
      divider(),
      h2("9.1 Non-Negotiable Security Controls"),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [480, 4080, 4800],
        rows: [
          new TableRow({ children: [headerCell("", BLUE_DARK, "FFFFFF", 480), headerCell("Control", BLUE_DARK, "FFFFFF", 4080), headerCell("Implementation requirement", BLUE_DARK, "FFFFFF", 4800)] }),
          ...[
            ["API keys server-side only", "Injected via environment variables or secret manager. Never committed to git. Never exposed to client. Rotate on any suspicion of leak."],
            ["PII redacted before logs and memory", "Email addresses, names, order references stripped or pseudonymised before any log.write(), trace.set(), or memory.persist(). Redaction runs before the trace stage."],
            ["Structured + protected logging", "JSON logs only. Log levels: DEBUG/INFO/WARN/ERROR/SECURITY. SECURITY level for policy violations and auth failures. No duplication of personal data across log tiers."],
            ["Least privilege on all connectors", "Each connector has its own service account with exactly the permissions it needs. Read-only where possible. Write operations require policy approval."],
            ["Human approval on sensitive actions", "Any action tagged sensitive in PolicyRule requires DecisionResult.required_human_review = True. Auto-send never fires on flagged decisions."],
            ["Memory isolation per account/client", "MemoryItem scope enforced at storage level. No query crosses account boundary. TTL enforced by the storage layer, not caller."],
            ["Adversarial input sanitisation", "All external content (email body, attachment text, subject lines) treated as untrusted. Injection patterns stripped before NLP pipeline."],
            ["Secrets scan in CI", "gitleaks or equivalent runs on every PR. Any detected secret blocks the merge."],
          ].map(([ctrl, impl]) => new TableRow({ children: [
            cell("", { fill: GREEN_FILL, bold: true, color: GREEN, width: 480, align: AlignmentType.CENTER }),
            cell(ctrl, { fill: GREEN_FILL, bold: true, width: 4080 }),
            cell(impl, { fill: GREEN_FILL, width: 4800 }),
          ]})),
        ],
      }),
      spacer(120, 120),
      h2("9.2 CNIL Compliance Requirements (France)"),
      bullet("Data minimisation: collect only what is needed for the specific processing purpose"),
      bullet("Explainable logging: logs must contain enough context to explain why a decision was made"),
      bullet("Human supervision: every automated decision above a defined risk threshold requires human review"),
      bullet("Justified retention: 3-tier retention policy — security logs (6–12 months), operational traces (30–90 days), conversational content (business-justified, short default)"),
      bullet("Purpose separation: logs for security auditing must not be mixed with logs for product analytics"),
      bullet("Continuous quality control: AI output quality must be monitored and documented on an ongoing basis"),
      spacer(120, 120),
      h2("9.3 Data Retention Policy"),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [2400, 2400, 2400, 2160],
        rows: [
          new TableRow({ children: [headerCell("Tier", BLUE_DARK, "FFFFFF", 2400), headerCell("Content", BLUE_DARK, "FFFFFF", 2400), headerCell("Retention", BLUE_DARK, "FFFFFF", 2400), headerCell("PII handling", BLUE_DARK, "FFFFFF", 2160)] }),
          new TableRow({ children: [cell("Security logs", { fill: RED_FILL, bold: true, width: 2400 }), cell("Policy violations, auth failures, injection attempts", { fill: RED_FILL, width: 2400 }), cell("6–12 months", { fill: RED_FILL, width: 2400 }), cell("Redacted, protected", { fill: RED_FILL, width: 2160 })] }),
          new TableRow({ children: [cell("Operational traces", { fill: YELLOW_FILL, bold: true, width: 2400 }), cell("StepTrace, latency, tokens, decisions, model versions", { fill: YELLOW_FILL, width: 2400 }), cell("30–90 days", { fill: YELLOW_FILL, width: 2400 }), cell("No raw PII; metadata only", { fill: YELLOW_FILL, width: 2160 })] }),
          new TableRow({ children: [cell("Conversational content", { fill: GREEN_FILL, bold: true, width: 2400 }), cell("Email bodies, drafts, attachment extracts", { fill: GREEN_FILL, width: 2400 }), cell("Short default; business-justified", { fill: GREEN_FILL, width: 2400 }), cell("PII pseudonymised or deleted", { fill: GREEN_FILL, width: 2160 })] }),
        ],
      }),
      pageBreak(),

      // ══════════════════════════════════════════
      // 10. RISK REGISTER
      // ══════════════════════════════════════════
      h1("10. Risk Register"),
      divider(),
      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [2400, 1200, 1200, 4560],
        rows: [
          new TableRow({ children: [headerCell("Risk", BLUE_DARK, "FFFFFF", 2400), headerCell("Likelihood", BLUE_DARK, "FFFFFF", 1200), headerCell("Impact", BLUE_DARK, "FFFFFF", 1200), headerCell("Mitigation", BLUE_DARK, "FFFFFF", 4560)] }),
          new TableRow({ children: [cell("Hallucination reaches customer", { fill: RED_FILL, bold: true, width: 2400 }), cell("Medium", { fill: RED_FILL, width: 1200, align: AlignmentType.CENTER }), cell("Critical", { fill: RED_FILL, color: RED, bold: true, width: 1200, align: AlignmentType.CENTER }), cell("Fact registry + validator blocks unsupported claims. Fallback template on block. Human review on low confidence.", { fill: RED_FILL, width: 4560 })] }),
          new TableRow({ children: [cell("Prompt injection via email body", { bold: true, width: 2400 }), cell("Medium", { width: 1200, align: AlignmentType.CENTER }), cell("High", { color: ORANGE, bold: true, width: 1200, align: AlignmentType.CENTER }), cell("Adversarial input cleaning strips injection patterns before NLP. All external content treated as untrusted.", { width: 4560 })] }),
          new TableRow({ children: [cell("ERP/CRM connector outage", { fill: RED_FILL, bold: true, width: 2400 }), cell("Medium", { fill: RED_FILL, width: 1200, align: AlignmentType.CENTER }), cell("High", { fill: RED_FILL, color: ORANGE, bold: true, width: 1200, align: AlignmentType.CENTER }), cell("Retry + circuit breaker + fallback template. Ticket routes to human review if connector exhausted. No crash.", { fill: RED_FILL, width: 4560 })] }),
          new TableRow({ children: [cell("Prompt regression in production", { bold: true, width: 2400 }), cell("High", { width: 1200, align: AlignmentType.CENTER }), cell("High", { color: ORANGE, bold: true, width: 1200, align: AlignmentType.CENTER }), cell("Eval harness in CI blocks merge on regression. Prompt registry traces every change to a PR.", { width: 4560 })] }),
          new TableRow({ children: [cell("PII leak in logs", { fill: RED_FILL, bold: true, width: 2400 }), cell("Low", { fill: RED_FILL, width: 1200, align: AlignmentType.CENTER }), cell("Critical", { fill: RED_FILL, color: RED, bold: true, width: 1200, align: AlignmentType.CENTER }), cell("Redaction layer runs before every log.write() and trace.set(). PII audit in CI. CNIL notification procedure documented.", { fill: RED_FILL, width: 4560 })] }),
          new TableRow({ children: [cell("Duplicate tickets or double-send", { bold: true, width: 2400 }), cell("High", { width: 1200, align: AlignmentType.CENTER }), cell("Medium", { color: "888888", width: 1200, align: AlignmentType.CENTER }), cell("Idempotency keys on all inbound messages and all write actions. DuplicateSuppressed event logged.", { width: 4560 })] }),
          new TableRow({ children: [cell("Customer data cross-contamination", { fill: RED_FILL, bold: true, width: 2400 }), cell("Low", { fill: RED_FILL, width: 1200, align: AlignmentType.CENTER }), cell("Critical", { fill: RED_FILL, color: RED, bold: true, width: 1200, align: AlignmentType.CENTER }), cell("Memory and fact registry scoped at account level enforced by storage layer. Penetration test before multi-tenant go-live.", { fill: RED_FILL, width: 4560 })] }),
          new TableRow({ children: [cell("Config missing crashes app at onboarding", { bold: true, width: 2400 }), cell("High", { width: 1200, align: AlignmentType.CENTER }), cell("Medium", { color: "888888", width: 1200, align: AlignmentType.CENTER }), cell("ConfigValidator runs before launch with clear human-readable error messages. Setup wizard validates in real time.", { width: 4560 })] }),
        ],
      }),
      pageBreak(),

      // ══════════════════════════════════════════
      // 11. SUCCESS MILESTONES
      // ══════════════════════════════════════════
      h1("11. Success Milestones"),
      divider(),
      para("These are the concrete checkpoints that signal readiness to move to the next stage. Each one is observable and verifiable, not a feeling."),
      spacer(80, 80),

      new Table({
        width: { size: 9360, type: WidthType.DXA },
        columnWidths: [1400, 2000, 3960, 2000],
        rows: [
          new TableRow({ children: [headerCell("Milestone", BLUE_DARK, "FFFFFF", 1400), headerCell("When", BLUE_DARK, "FFFFFF", 2000), headerCell("Observable evidence", BLUE_DARK, "FFFFFF", 3960), headerCell("Opens door to", BLUE_DARK, "FFFFFF", 2000)] }),
          new TableRow({ children: [cell("M0 — Unbreakable base", { fill: RED_FILL, bold: true, color: RED, width: 1400 }), cell("End of Phase 0 (Wk 4)", { fill: RED_FILL, width: 2000 }), cell("100-ticket smoke test completes with zero unclassified exceptions. All transitions tested. Zero dict at agent boundaries.", { fill: RED_FILL, width: 3960 }), cell("First internal demo", { fill: RED_FILL, width: 2000 })] }),
          new TableRow({ children: [cell("M1 — Production-ready", { fill: ORANGE_FILL, bold: true, color: ORANGE, width: 1400 }), cell("End of Phase 1 (Wk 10)", { fill: ORANGE_FILL, width: 2000 }), cell("CI pipeline green. Eval harness running. 48h stable demo environment. Injection tests all blocked.", { fill: ORANGE_FILL, width: 3960 }), cell("First paying customer", { fill: ORANGE_FILL, width: 2000 })] }),
          new TableRow({ children: [cell("M2 — First B2B revenue", { fill: GREEN_FILL, bold: true, color: GREEN, width: 1400 }), cell("Wk 12–14", { fill: GREEN_FILL, width: 2000 }), cell("Contract signed. Real tickets flowing. p95 < 5s. Human review rate below 30%. Zero critical incidents.", { fill: GREEN_FILL, width: 3960 }), cell("Case study, pricing model", { fill: GREEN_FILL, width: 2000 })] }),
          new TableRow({ children: [cell("M3 — Smart platform", { fill: BLUE_PALE, bold: true, color: BLUE_DARK, width: 1400 }), cell("End of Phase 2 (Wk 18)", { fill: BLUE_PALE, width: 2000 }), cell("3 active accounts. Attachment handling live. KB dashboard showing data. Memory system stable. p95 < 3s.", { fill: BLUE_PALE, width: 3960 }), cell("Series A narrative", { fill: BLUE_PALE, width: 2000 })] }),
          new TableRow({ children: [cell("M4 — Series A ready", { fill: GRAY_FILL, bold: true, color: BLUE_DARK, width: 1400 }), cell("End of Phase 3 (Wk 28)", { fill: GRAY_FILL, width: 2000 }), cell("10+ accounts. Measurable EBIT impact per customer documented. SOC 2 or CNIL audit in progress. Token cost down 30%.", { fill: GRAY_FILL, width: 3960 }), cell("Scale fundraising", { fill: GRAY_FILL, width: 2000 })] }),
        ],
      }),
      spacer(200, 120),
      divider(BLUE_MID),
      spacer(80, 80),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: "CS AI Engine — Product & Engineering Roadmap  ·  v1.0  ·  April 2026", font: "Arial", size: 18, color: "888888", italics: true })],
      }),
      new Paragraph({
        alignment: AlignmentType.CENTER,
        children: [new TextRun({ text: "CONFIDENTIAL — Do not distribute outside the founding team", font: "Arial", size: 18, bold: true, color: BLUE_DARK })],
        spacing: { before: 60, after: 60 },
      }),
    ],
  }],
});

Packer.toBuffer(doc).then(buffer => {
  const outputPath = 'C:\\Users\\HP\\Desktop\\AI\\CS_AI_Engine_Startup_Roadmap.docx';
  fs.writeFileSync(outputPath, buffer);
  console.log(`Done: ${outputPath}`);
  console.log(`File size: ${buffer.length} bytes`);
});
