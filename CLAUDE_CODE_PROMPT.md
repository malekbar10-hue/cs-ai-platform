# Claude Code Prompts — Generic CS AI Platform
## Paste each section into Claude Code in VS Code when ready for that phase.

---

## ALREADY DONE (do not re-run these)
- Security fix: `.env` and `.gitignore` created ✅
- `nlp.py` with sentence-transformers + ChromaDB ✅
- `connector.py` redesigned: generic `ERPConnector` + `CRMConnector` ✅
- `config.json` cleaned up with generic `endpoint` + `auth` fields ✅

---

## PHASE 1 — Complete the Intelligence Layer

### Prompt 1.1 — Confidence Scoring

```
Add a confidence scoring system to my CS AI.

My project has:
- main.py — AI engine with detection and response generation
- nlp.py — embeddings-based NLP that already returns confidence scores per detection
- app.py — Streamlit dashboard with approve/modify/reject workflow
- config.json — project config

TASK: Create a new file confidence.py with a ConfidenceScorer class.

class ConfidenceScorer:
    def score(self, nlp_confidence, emotion, intensity, intent, customer_profile, action_risk) -> dict:
        Returns:
        {
          "overall": float 0.0-1.0,
          "recommendation": "auto_send" | "human_review" | "supervisor_review",
          "factors": {
            "nlp": float,
            "emotion_risk": float,
            "customer_risk": float,
            "action_risk": float,
            "intent_complexity": float
          }
        }

Scoring weights:
- nlp_confidence: weight 0.30 (value comes directly from nlp.py cosine similarity)
- emotion_risk: weight 0.25 (Angry/Urgent Very High = 0.0, Satisfied = 1.0, linear scale between)
- customer_risk: weight 0.25 (escalating trajectory = 0.0, new customer = 0.5, satisfied repeat = 1.0)
- action_risk: weight 0.15 (High risk ERP action = 0.0, Medium = 0.4, Low = 0.8, no action = 1.0)
- intent_complexity: weight 0.10 (escalate/complaint = 0.1, cancel = 0.3, tracking/info = 1.0)

Thresholds:
- overall >= 0.85 -> "auto_send"
- overall >= 0.50 -> "human_review"
- overall < 0.50  -> "supervisor_review"

Hard override rules (these always apply regardless of score):
- ERP action risk is "High" -> force "supervisor_review"
- emotion is "Angry" AND intensity in ["High", "Very High"] -> minimum "human_review"
- customer trajectory is "Escalating" -> minimum "human_review"
- No profile exists for this customer (first contact) -> minimum "human_review"

Add these thresholds to config.json under a new "confidence" key:
{
  "auto_send_threshold": 0.85,
  "human_review_threshold": 0.50,
  "auto_send_enabled": false
}

auto_send_enabled is false by default. The system will SHOW the recommendation but always require human approval until this is explicitly set to true.

Update app.py:
- Import and call ConfidenceScorer after generating a draft
- Show the confidence score in the Analysis panel: "Confidence: 78% — Human review recommended"
- Color code: green >= 0.85, yellow 0.50-0.85, red < 0.50
- Add "confidence_score" and "confidence_recommendation" fields to the log entry

Do NOT change connector.py, nlp.py, or any JSON data files.
Do NOT break any existing app.py functionality.
```

---

### Prompt 1.2 — Multi-Model Routing

```
Add config-driven model routing to my CS AI so different complexity levels use different AI models.

Currently: "gpt-4.1-mini" is hardcoded in app.py.

TASK:

1. Update config.json — add a model routing config:
{
  "ai": {
    "models": {
      "simple":   { "model": "gpt-4.1-mini", "max_tokens": 500,  "temperature": 0.3 },
      "standard": { "model": "gpt-4.1-mini", "max_tokens": 1000, "temperature": 0.5 },
      "complex":  { "model": "gpt-4.1",      "max_tokens": 1500, "temperature": 0.7 }
    },
    "routing": {
      "simple_intents":      ["tracking", "info", "document_request"],
      "complex_emotions":    ["Angry", "Urgent"],
      "complex_intensities": ["Very High", "High"],
      "complex_intents":     ["escalate", "complaint", "cancel"]
    }
  }
}

2. Add a function select_model(emotion, intensity, intent, confidence_score, config) -> dict in main.py:
- If intent in complex_intents OR (emotion in complex_emotions AND intensity in complex_intensities) -> return models["complex"]
- If intent in simple_intents AND confidence_score > 0.80 AND emotion in ["Neutral", "Satisfied"] -> return models["simple"]
- Otherwise -> return models["standard"]

3. Update the OpenAI client call in app.py to use the selected model dict (model name, max_tokens, temperature).

4. Log which model was used in each interaction's log entry.

5. If config only has the old single "model" field (backward compatibility), use that model for everything.

Do NOT change connector.py, nlp.py, or JSON data files.
```

---

### Prompt 1.3 — Semantic Knowledge Base

```
Upgrade the knowledge base search in my CS AI from keyword matching to semantic retrieval.

Current: search_knowledge_base() in main.py scores entries by matching intent, topic, and keywords.
My nlp.py already has sentence-transformers and ChromaDB running.

TASK: Add semantic KB retrieval to nlp.py.

1. Add to the NLPEngine class in nlp.py:

  def build_kb_embeddings(self, entries: list):
    - Embed each entry's title + content combined
    - Store in a ChromaDB collection named "knowledge_base"
    - Metadata per entry: id, title, intents list, topics list
    - Call this during --build and at startup if collection is empty

  def search_kb(self, query: str, intent: str = None, topic: str = None, max_results: int = 3) -> list:
    - Embed the query
    - Query the knowledge_base collection for top 5 by cosine similarity
    - Apply boosts: +0.10 if intent matches entry metadata, +0.05 if topic matches
    - Return top max_results entries sorted by boosted score, each with a "relevance" float field added

2. Update main.py:
- Rename existing search_knowledge_base() to search_knowledge_base_legacy() (keep as fallback)
- Add a new search_knowledge_base() that calls nlp_engine.search_kb() if available, falls back to legacy if not

3. Make sure knowledge_base.json entries are loaded and embedded when nlp.py --build is run.

4. Update format_kb_context() to include relevance score so the AI knows how confident the KB match is.

Do NOT change connector.py, config.json, or app.py (except the search_knowledge_base import if needed).
```

---

## PHASE 2 — Generic Communication Channel

### Prompt 2.1 — Generic Channel Reader + Sender

```
Build generic communication channel classes that read inbound messages and send outbound responses.
This must be 100% config-driven — no company-specific logic in the code.

TASK:

1. Create a file channels.py with:

  a) An InboundMessage dataclass:
  {
    message_id: str,
    thread_id: str,
    from_address: str,
    from_name: str,
    subject: str,
    body: str,
    received_at: datetime,
    attachments: list,
    is_reply: bool,
    raw_headers: dict
  }

  b) A BaseChannelReader abstract class:
    - fetch_new(since_minutes=5) -> list[InboundMessage]
    - mark_read(message_id)
    - get_thread(thread_id) -> list[InboundMessage]

  c) An EmailReader(BaseChannelReader) that reads from IMAP:
    - Initialized from communication config (server, port, username, password from ENV, ssl, folder)
    - Parses HTML and plain-text emails, prefers plain text
    - Cleans reply-chain (strip quoted previous messages)
    - Detects thread continuations via In-Reply-To header

  d) A BaseChannelSender abstract class:
    - send_reply(original: InboundMessage, body: str, attachments=None) -> bool
    - send_new(to: str, subject: str, body: str, attachments=None) -> bool

  e) An EmailSender(BaseChannelSender):
    - SMTP with TLS
    - Preserves threading headers (In-Reply-To, References)
    - Appends company signature from communication config
    - Initialized from communication config (server, port, from_address, password from ENV)

2. Add communication config to config.json:
{
  "communication": {
    "inbound": {
      "channel": "email",
      "server": "",
      "port": 993,
      "username": "",
      "password_env_var": "EMAIL_IMAP_PASSWORD",
      "folder": "INBOX",
      "ssl": true
    },
    "outbound": {
      "channel": "email",
      "smtp_server": "",
      "smtp_port": 587,
      "username": "",
      "password_env_var": "EMAIL_SMTP_PASSWORD",
      "from_address": "",
      "from_name": "Customer Service",
      "signature": "Best regards,\nCustomer Service Team"
    }
  }
}

3. Create a test script test_channels.py:
  - Connects using config
  - Fetches the 3 most recent emails
  - Prints: from, subject, body preview (200 chars), is_reply
  - Does NOT send anything

4. Add a get_channel_reader(config) and get_channel_sender(config) factory function.

Do NOT modify main.py, app.py, or connector.py yet.
The channel layer is standalone until Phase 2.2 integrates it.
```

---

### Prompt 2.2 — Ticket System + Inbox Dashboard

```
Build a ticket lifecycle system and upgrade the Streamlit dashboard to a multi-ticket inbox.

My project now has:
- main.py + nlp.py — AI engine
- app.py — single-conversation Streamlit dashboard
- channels.py — email reader/sender (just created)
- connector.py — ERP/CRM data layer
- config.json — configuration

TASK:

1. Create tickets.py:

  Ticket dataclass:
  {
    ticket_id: str (uuid),
    status: str — "new" | "triaged" | "drafting" | "pending_approval" | "sent" | "resolved" | "closed",
    priority: str — "Normal" | "High" | "Critical",
    customer_email: str,
    customer_name: str,
    subject: str,
    channel: str,
    created_at: datetime,
    updated_at: datetime,
    sla_deadline: datetime,
    emotion: str,
    intent: str,
    confidence: float,
    order_id: str or None,
    thread_id: str or None,
    messages: list of dicts {role, content, timestamp},
    erp_actions: list of dicts,
    metadata: dict
  }

  TicketManager class using SQLite (tickets.db):
  - create_ticket(inbound_message: InboundMessage) -> Ticket
  - get_ticket(ticket_id) -> Ticket
  - update_ticket(ticket_id, **changes) -> Ticket
  - list_tickets(status=None, priority=None) -> list[Ticket]
  - find_by_thread(thread_id) -> Ticket or None
  - get_sla_status(ticket) -> "on_track" | "warning" | "breached"
    (warning = less than 25% of SLA time remaining)
  - Compute sla_deadline from config["sla"][priority]["response_hours"] at ticket creation

2. Create app_inbox.py (do NOT modify existing app.py):

  Layout:
  - Left sidebar: filters (status, priority), SLA alert count, quick stats (open, warnings, breached today)
  - Main area in two modes:

  INBOX MODE (default):
  - Sortable table of tickets: priority icon | customer | subject | status | emotion | SLA countdown
  - Color coding: 🔴 breached, 🟡 warning, 🟢 on track
  - Click a row -> CONVERSATION MODE

  CONVERSATION MODE:
  - Full message thread (chat-style, with roles)
  - Customer message input OR email polling feeds new messages
  - AI analysis panel (emotion, intent, confidence, order info, customer profile) — same as current app.py
  - Draft review panel with Approve / Edit & Approve / Reject buttons
  - On approve: save to ticket, call EmailSender.send_reply(), update ticket status to "sent"
  - Back to inbox button

3. Create email_poller.py — a simple polling script:
  - Runs: python email_poller.py
  - Every N seconds (from config), calls EmailReader.fetch_new()
  - For each new email: call TicketManager.find_by_thread() — if found, add message to ticket; if not found, create new ticket and run initial NLP analysis
  - Writes to tickets.db

4. Run with: streamlit run app_inbox.py
   Keep app.py working as standalone fallback.

Do NOT change main.py, connector.py, or nlp.py.
```

---

## PHASE 3 — Generic ERP Integration

### Prompt 3.1 — Config-Driven ERP Connector

```
Implement the ERPConnector in connector.py so it actually calls a real REST API using
config-driven field mapping. No hardcoded API paths, no vendor-specific code.

Current connector.py has ERPConnector with NotImplementedError stubs.

TASK:

1. Create a new file erp_mapping.json (template — company fills this in):
{
  "endpoints": {
    "get_order":    "GET /orders/{order_id}",
    "list_orders":  "GET /orders?fields=id&limit=500",
    "update_order": "PATCH /orders/{order_id}"
  },
  "field_map": {
    "status":        "status",
    "delivery_date": "expected_delivery",
    "stock":         "stock_qty",
    "customer":      "customer_name",
    "priority":      "priority",
    "reason":        "hold_reason"
  },
  "status_map": {
    "PROCESSING": "Processing",
    "BLOCKED":    "Blocked",
    "SHIPPED":    "Shipped",
    "DELAYED":    "Delayed",
    "CANCELLED":  "Cancelled"
  },
  "reverse_status_map": {
    "Processing": "PROCESSING",
    "Blocked":    "BLOCKED",
    "Shipped":    "SHIPPED",
    "Delayed":    "DELAYED",
    "Cancelled":  "CANCELLED"
  }
}

2. Implement ERPConnector fully:

  __init__(config):
  - Load erp_mapping.json from the path in config["erp"].get("mapping_file", "erp_mapping.json")
  - Initialize a requests.Session
  - Apply auth from config["erp"]["auth"]:
    * type "bearer"  -> session.headers["Authorization"] = "Bearer {token from ENV}"
    * type "basic"   -> session.auth = (username, password from ENV)
    * type "api_key" -> session.headers[header_name] = key from ENV
    * type "oauth2"  -> implement client_credentials flow, cache token, refresh on expiry

  _call(method, path_template, path_params=None, body=None) -> dict:
  - Build URL: self.endpoint + path filled from path_params
  - Execute method (GET/PATCH/POST)
  - Handle errors: 401 -> refresh auth, 429 -> retry after backoff, 5xx -> log and raise
  - Return parsed JSON or raise clear exception

  _map_to_standard(raw_order) -> dict:
  - Translate raw API response fields to our standard schema using field_map
  - Apply status_map to normalize status values
  - Return {status, delivery_date, stock, customer, priority, reason}

  _map_to_erp(changes) -> dict:
  - Translate our standard change dict to ERP field names using reverse field_map
  - Apply reverse_status_map for status changes

  get_order(order_id) -> calls _call + _map_to_standard
  list_order_ids() -> calls _call, extracts IDs
  update_order(order_id, changes) -> calls _map_to_erp then _call

3. Add ERPConnector to the get_connector() factory: type "erp_api" -> ERPConnector(config)

4. Add test_connection() method to ERPConnector:
  - Makes a simple GET request to verify the endpoint is reachable and auth works
  - Returns {"ok": True/False, "message": str}

5. Add a MockERPConnector that extends JSONConnector but also validates the erp_mapping.json
   structure — useful for testing the mapping logic without a real ERP.

Do NOT change main.py, nlp.py, app.py, or any JSON data files.
Do NOT add any SAP, Oracle, or vendor-specific code. Pure generic REST.
```

---

### Prompt 3.2 — Generic Auth Abstraction

```
Add a reusable auth module for all external API connections in my CS AI.

My project uses credentials to connect to: ERP API, CRM API, email (IMAP/SMTP).
All credentials must come from environment variables — never from config files.

TASK: Create auth.py with an AuthManager class.

class AuthManager:

  @staticmethod
  def apply_to_session(session, auth_config: dict):
    """Apply authentication to a requests.Session based on auth config."""
    Supports:
    - {"type": "bearer", "token_env_var": "ERP_TOKEN"}
      -> session.headers["Authorization"] = f"Bearer {os.environ[token_env_var]}"
    - {"type": "basic", "username_env_var": "ERP_USER", "password_env_var": "ERP_PASS"}
      -> session.auth = (os.environ[username_env_var], os.environ[password_env_var])
    - {"type": "api_key", "header": "X-API-Key", "key_env_var": "ERP_API_KEY"}
      -> session.headers[header] = os.environ[key_env_var]
    - {"type": "oauth2_client_credentials", "token_url_env_var": "OAUTH_TOKEN_URL",
       "client_id_env_var": "OAUTH_CLIENT_ID", "client_secret_env_var": "OAUTH_SECRET"}
      -> request token, cache it, refresh 60s before expiry

  @staticmethod
  def get_token_oauth2(token_url, client_id, client_secret) -> str:
    """Request a new OAuth2 client_credentials token. Returns the access token string."""

  @staticmethod
  def validate_env_vars(auth_config: dict) -> list:
    """Returns list of missing environment variable names so startup can fail fast with a clear message."""

Update ERPConnector and CRMConnector to use AuthManager.apply_to_session() instead of inline auth logic.

Add a check at startup (in get_connector()): call AuthManager.validate_env_vars() for the selected connector's auth config. If any required ENV vars are missing, raise a clear error: "Missing required environment variable: ERP_TOKEN — add it to your .env file"

Do NOT change main.py, nlp.py, app.py, or JSON data files.
```

---

## PHASE 4 — Generic Escalation Engine

### Prompt 4.1 — Rule-Based Escalation Engine

```
Build a generic escalation engine that reads rules from a JSON config file and executes actions.
No hardcoded escalation logic. Every company defines its own rules in escalation_rules.json.

TASK:

1. Create escalation_rules.json (template):
{
  "rules": [
    {
      "id": "rule_01",
      "name": "Critical angry customer",
      "enabled": true,
      "cooldown_minutes": 60,
      "conditions": {
        "emotion": ["Angry"],
        "intensity": ["Very High", "High"],
        "order_priority": ["Critical", "High"]
      },
      "actions": [
        {
          "type": "notify_email",
          "to_env_var": "SUPERVISOR_EMAIL",
          "subject": "URGENT CS Escalation: {customer_name} | Order {order_id}",
          "body_template": "Customer: {customer_name}\nEmotion: {emotion} ({intensity})\nIntent: {intent}\nOrder: {order_id}\n\nCustomer message:\n{customer_message}",
          "include_draft": true
        }
      ]
    },
    {
      "id": "rule_02",
      "name": "SLA warning",
      "enabled": true,
      "cooldown_minutes": 120,
      "conditions": {
        "sla_status": ["warning", "breached"]
      },
      "actions": [
        {
          "type": "notify_webhook",
          "url_env_var": "SLACK_WEBHOOK_URL",
          "message": "⚠️ SLA {sla_status}: {customer_name} ticket has been waiting {hours_open}h"
        }
      ]
    },
    {
      "id": "rule_03",
      "name": "Repeated contact unresolved",
      "enabled": true,
      "cooldown_minutes": 0,
      "conditions": {
        "interaction_count": {"greater_than": 2},
        "last_intent_same": true
      },
      "actions": [
        {
          "type": "flag_for_supervisor",
          "message": "Customer contacted {interaction_count} times for the same issue"
        }
      ]
    }
  ]
}

2. Create escalation.py:

  class EscalationEngine:

    __init__(rules_file="escalation_rules.json"):
    - Load rules from JSON
    - Initialize action executors

    evaluate(context: dict) -> list[dict]:
    - context has: emotion, intensity, intent, topic, order_id, order_priority,
                   customer_name, customer_message, interaction_count, sla_status,
                   hours_open, last_intent, draft
    - Evaluate each enabled rule's conditions against context
    - For matching rules: check cooldown (skip if fired recently for this ticket)
    - Execute matching rules' actions
    - Return list of fired rule results

    _match_conditions(rule_conditions, context) -> bool:
    - Supports: list match (emotion in list), numeric comparison (greater_than, less_than), bool match
    - Returns True only if ALL conditions match

  Action executors (each a separate method or small class):
  - notify_email(action_config, context): send email via SMTP using config
  - notify_webhook(action_config, context): POST JSON to webhook URL
  - flag_for_supervisor(action_config, context): set a flag in the ticket context
  - All templates support {variable} substitution from context dict

  Track fired rules: use a simple dict {ticket_id: [{rule_id, fired_at}]}
  For cooldown check: if rule fired for this ticket within cooldown_minutes, skip it.

3. Integrate into app.py (and app_inbox.py when ready):
- After a message is analyzed, call escalation_engine.evaluate(context)
- If any rules fire: show alert banners in the dashboard ("⚠ Escalation triggered: {rule_name}")
- Log escalation events with the interaction

4. Add get_escalation_engine(config) factory that loads the right rules file.
   Default: "escalation_rules.json". Company override: config["escalation"]["rules_file"].

Do NOT change connector.py, nlp.py, or JSON data files.
No hardcoded email addresses, Slack URLs, or escalation paths anywhere in the code.
```

---

## PHASE 5 — Company Template System

### Prompt 5.1 — Multi-Company Structure

```
Restructure my CS AI to support multiple companies, each with its own config folder.
The engine code never changes per company. Only config files change.

Current structure: all config files (config.json, knowledge_base.json, etc.) are in the project root.

TASK:

1. Create this folder structure (move existing files, do not delete):

cs_ai/
  engine/
    main.py
    nlp.py
    app.py
    app_inbox.py
    connector.py
    channels.py
    tickets.py
    escalation.py
    confidence.py
    auth.py
  
  companies/
    _template/
      config.json           (copy of current config.json with placeholder values)
      erp_mapping.json      (generic field mapping template)
      communication.json    (email/channel config template)
      escalation_rules.json (escalation rules template)
      knowledge_base.json   (empty KB with structure comments)
      orders_mock.json      (copy of current orders.json for demo)
    
    default/                (copy of current working config — rename to your first company later)
      config.json           (current config.json)
      knowledge_base.json   (current knowledge_base.json)
      orders_mock.json      (current orders.json)
      erp_mapping.json      (minimal, maps our schema to itself for JSON mock)
      escalation_rules.json (current basic rules)
  
  data/
    default/
      logs.json             (current logs.json)
      customer_profiles.json (current customer_profiles.json)
      tickets.db            (SQLite tickets, created fresh per company)
      chroma_db/            (current chroma_db folder)

2. Create run.py in the project root:
  - Usage: python run.py --company default
  - Loads config from companies/{company}/config.json
  - Sets working paths for data to data/{company}/
  - Passes company_config to all engine components
  - Starts the Streamlit app: streamlit run engine/app.py -- --company {company}

3. Update engine/main.py, engine/app.py, engine/connector.py to accept a config_path parameter
   instead of hardcoding "config.json". Read config from the path provided by run.py.

4. Create setup.py:
  - Usage: python setup.py --company default
  - Validates: are all required config fields filled? are ENV vars set? does ERP connect?
  - Runs: python engine/nlp.py --build --company default (builds embeddings for this company's KB)
  - Prints a readiness checklist with green/red status per item

5. Update all file path references in the code to use the company data directory,
   not hardcoded filenames like "logs.json" or "orders.json".

6. After restructuring: run setup.py --company default and verify the app starts correctly.
   Fix any import errors before moving on.
```

---

## PHASE 6 — Multi-Agent Pipeline

### Prompt 6.1 — Agent Framework

```
Refactor the CS AI into a pipeline of specialized agents.

Current: all logic runs in analyze_and_generate() in app.py.

TASK: Create an agents/ directory inside engine/ with these files.

agents/base.py:
  class BaseAgent:
    name: str
    def run(self, context: dict) -> dict  (receives context, returns enriched context)
    def __call__(self, context): return self.run(context)

agents/triage.py — TriageAgent(BaseAgent):
  run(context) where context has: {raw_message, inbound_email (optional), company_config}
  - Run NLP: detect language, emotion, intensity, intent, topic (call nlp.py)
  - Look up order from ERP connector
  - Look up customer profile from CRM connector
  - Calculate preliminary priority
  - Determine route: "auto" | "standard" | "priority" | "supervisor"
    (supervisor if: Angry Very High + Critical order, or trajectory Escalating + 3+ contacts)
  - Return context enriched with all analysis fields + "route" key

agents/response.py — ResponseAgent(BaseAgent):
  run(context) where context has all TriageAgent output
  - Build system prompt (call main.py build_system_prompt)
  - Search KB (call nlp.py search_kb)
  - Search history (call main.py search_history)
  - Get emotional trajectory
  - Call AI model (use selected model from confidence/complexity routing)
  - Detect suggested ERP action
  - Score confidence
  - Return context enriched with: {draft, confidence, suggested_action, model_used}

agents/qa.py — QAAgent(BaseAgent):
  run(context) where context has draft + full analysis
  - Make a second AI call with a QA system prompt that acts as a reviewer
  - QA prompt checks: does the draft mention the correct order data? is the tone right for emotion level? does it comply with KB policies? are there any red flags (wrong dates, impossible promises)?
  - Return: {"qa_result": "pass" | "needs_revision", "qa_feedback": str, "qa_flags": list}
  - If needs_revision: add "qa_revision_request" to context so ResponseAgent can retry

agents/orchestrator.py — Orchestrator:
  __init__(company_config): instantiate TriageAgent, ResponseAgent, QAAgent
  
  run(raw_message, inbound_email=None) -> dict:
  - Build initial context
  - Run TriageAgent
  - If route == "supervisor": return context with flag, skip response generation
  - Run ResponseAgent
  - Run QAAgent
  - If QAAgent says needs_revision AND retry_count < 2: re-run ResponseAgent with feedback, increment retry_count
  - Return final context with all fields + pipeline timing

  Each agent's run time is logged in context["pipeline_timings"][agent_name]

Update app.py (and app_inbox.py):
- Replace the analyze_and_generate() call with Orchestrator.run()
- Show QA result in the dashboard: if QA flagged issues, show them to the agent before they approve
- Show pipeline timings in a collapsible "Pipeline details" section

Keep analyze_and_generate() in app.py as a fallback if Orchestrator import fails.
```

---

## PHASE 7 — Self-Learning

### Prompt 7.1 — Correction Feedback Loop

```
Build a feedback loop that learns from every agent correction.

Current: when agents edit AI drafts in app.py, both original and final are saved to logs.json.
Nothing is done with this data yet.

TASK: Create learning.py.

class FeedbackAnalyzer:

  analyze_correction(original: str, final: str, context: dict) -> dict:
  - If original == final (no changes): return None (nothing to learn)
  - Make an AI call to compare and classify the correction:
    System prompt: "You are a QA analyst. Compare these two CS email drafts and classify the edit."
    Return JSON: {
      "correction_type": one of ["tone", "factual", "added_info", "removed_info", "policy", "minor"],
      "severity": one of ["critical", "significant", "minor"],
      "lesson": "one-sentence description of what the AI should do differently next time",
      "example_before": first 100 chars of the changed section,
      "example_after": first 100 chars of the corrected section
    }
  - Store result in lessons table (SQLite): {id, timestamp, company, customer_name, emotion, intensity, intent, topic, correction_type, severity, lesson, example_before, example_after}

  get_lessons(emotion=None, intent=None, topic=None, customer_name=None, limit=3) -> list[str]:
  - Query the lessons table for matching records
  - Priority: same customer > same emotion+intent > same intent only
  - Return list of lesson strings (just the "lesson" field), most recent first, limited to 3

  get_report(days=30) -> dict:
  - Count: total interactions, total corrections, correction rate (%)
  - Most common correction_type
  - Intents with highest correction rate
  - Trend: is correction rate improving? (compare first half vs second half of period)

Update main.py build_system_prompt():
- Accept an optional lessons: list[str] parameter
- If lessons provided, add a "LEARNED FROM PAST CORRECTIONS" block at the end:
  "Based on past corrections in similar situations:\n- {lesson1}\n- {lesson2}"

Update app.py:
- After an "approved modified" action: call FeedbackAnalyzer.analyze_correction() in background
- Call FeedbackAnalyzer.get_lessons() before generating a draft and pass lessons to build_system_prompt()

Add a "Learning" section to pages/1_Analytics.py:
- Correction rate over time (line chart)
- Top correction types (bar chart)
- 10 most recent lessons (table)
- "Is the AI improving?" — show trend direction

Do NOT change connector.py, nlp.py, or JSON data files.
```

---

## How to Use These Prompts

Copy each prompt block (the text between the triple backticks) and paste it into Claude Code in VS Code.

Work in this order:
1. Phase 1.1 (Confidence scoring)
2. Phase 1.2 (Multi-model routing)
3. Phase 1.3 (Semantic KB)
4. Phase 2.1 (Channel reader/sender)
5. Phase 2.2 (Tickets + inbox)
6. Phase 3.1 (ERP connector) — when you have an ERP to connect
7. Phase 3.2 (Auth module) — alongside 3.1
8. Phase 4.1 (Escalation engine)
9. Phase 5.1 (Multi-company structure) — before onboarding a second client
10. Phase 6.1 (Multi-agent pipeline)
11. Phase 7.1 (Self-learning)

After each phase, test the app: streamlit run app.py
After Phase 5.1, switch to: python run.py --company default

For a new client: copy companies/_template/ to companies/client_name/, fill in the configs, run python setup.py --company client_name.
