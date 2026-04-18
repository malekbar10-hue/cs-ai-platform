# CS AI — What We Built and Where We're Going
**Simple Version — No Technical Jargon**
April 2026

---

## The Big Picture

Think of it like this.

We built a very smart engine for a car. The engine works. It's powerful, well-tested, and reliable. But right now it's sitting in a garage with no body, no doors, no seats, no dashboard, and no license plate.

Before a company will drive it on the road, they need the full car — not just the engine.

That's what this roadmap is about.

---

## What We Already Built (The Engine)

Here's everything the system can do right now, in plain language:

**It reads customer emails and immediately understands:**
- What language it's written in (English, French, mixed)
- How the customer is feeling (angry, calm, urgent, anxious)
- What they want (track order, get refund, cancel, complain)
- What their order is about

**It decides how urgent the situation is:**
- If the customer is very angry → sends it to a human supervisor automatically
- If the deadline for answering is almost missed → escalates immediately
- If the customer has complained 3 times before → treats it as a priority
- If it's a spam or out-of-office reply → ignores it automatically

**It checks the facts before writing anything:**
- Looks up the real order data from the ERP system
- Stores only verified facts — delivery dates, prices, statuses
- The AI is not allowed to write anything that isn't backed by a real fact
- If the customer says "my order was shipped last week" but the ERP says "still processing" → it flags the contradiction and blocks the response

**It writes a professional response:**
- Chooses the right tone based on how the customer is feeling
- Writes in the customer's language
- Uses only facts it verified — no guessing, no inventing
- Reviews the draft itself and rewrites it if it's not good enough (up to 2 times)

**It has a safety net:**
- If something goes wrong (ERP is down, customer is too angry, missing info) → sends a pre-written safe email instead of making something up
- 8 pre-written safe emails: 4 situations × 2 languages (English and French)

**It remembers customers:**
- If a customer contacted you before, it remembers their last emotion and what they wanted
- Uses that memory to personalise the next response

**It never forgets to protect privacy:**
- Removes emails and phone numbers from all logs automatically
- Keeps a full record of every decision made, for auditing

**It tests itself:**
- 50+ automatic checks that verify every part of the system works
- 21 fake customer emails that test the full pipeline automatically
- If quality drops below 80%, it blocks any code change from being applied

---

## What's Still Missing (The Car Body)

The engine is great. But companies won't use it yet because it's missing the things they need to feel safe and in control.

Here's what's missing, in plain language:

---

### Missing Piece 1 — Who Can Do What
**The problem:** Right now, anyone with access could see everything and approve anything. A real company needs to control who can read emails, who can approve responses, and who can change settings.

**What we need to add:**
- Login system (works with company's existing Google/Microsoft login)
- Different permission levels: viewer, agent, supervisor, admin, company owner
- Rules like "only a supervisor can approve a refund response"
- A log of every approval — who clicked approve, when, and for which ticket

**Why companies care:** Their IT and legal teams won't allow a system that has no access control. This is usually the first question they ask.

---

### Missing Piece 2 — Each Company's Data Stays Separate
**The problem:** If we have 10 companies using the system, their customer data must never mix. Company A cannot see Company B's emails, orders, or responses.

**What we need to add:**
- Each company gets its own completely separate space for data, memory, and logs
- Each company can have its own rules and its own version of the AI's instructions
- Hard walls between companies — not just folders, actual separation

**Why companies care:** The first question a buyer asks is "where does our data go and who can see it?" If we can't answer clearly, they won't sign.

---

### Missing Piece 3 — Passwords and Keys Are Stored Safely
**The problem:** Right now, sensitive credentials (API keys, email passwords, ERP access) are stored in config files. That's risky.

**What we need to add:**
- A proper secrets vault (like a locked safe for digital passwords)
- No passwords or keys in the code or any file in the repository
- A clear separation between test environment, pre-launch environment, and live environment
- Process for changing passwords without breaking the system

**Why companies care:** If a developer's laptop is stolen, no customer data should be at risk.

---

### Missing Piece 4 — A Screen Where Humans Can Review and Approve
**The problem:** When the AI decides a response needs human review (angry customer, refund request, etc.), right now there's no proper place for a human to go and handle it.

**What we need to add:**
- A screen showing all tickets waiting for human review
- For each ticket: the AI's draft, the facts it used, why it was flagged, the confidence score, the risk level
- The reviewer can edit the draft, approve it, or reassign it to someone else
- After the human sends their version, the system compares it to the AI's draft (to learn from the difference)

**Why companies care:** If there's no review screen, supervisors have no way to do their job. CNIL also legally requires this human override capability in Europe.

---

### Missing Piece 5 — A Dashboard So You Can See What's Happening
**The problem:** Right now the system logs everything, but it's raw data. No one can look at a screen and understand if the system is healthy or not.

**What we need to add:**
- A live dashboard showing:
  - How many tickets were answered automatically vs sent to a human
  - How often the AI was blocked for inventing facts
  - How often the safe pre-written email was used (and why)
  - How fast the system is responding
  - Which company is close to missing their response deadline
  - How much it's costing per company per day
  - Which version of the AI instructions is producing the best results

**Why companies care:** Without a dashboard, operations teams are flying blind. They won't trust a system they can't watch.

---

### Missing Piece 6 — Watching Quality After It Goes Live
**The problem:** Right now we test quality before releasing new code. But once the system is live, quality could slowly get worse and nobody notices until customers start complaining.

**What we need to add:**
- Automatically check a sample of real sent responses every day
- Score them the same way the pre-launch tests do
- Send an alert if quality is dropping
- Send an alert if the pre-written safe emails are being sent too often (means something is wrong)
- Send an alert if human reviewers are making big changes to AI drafts (means the AI is producing bad responses)

**Why companies care:** They want early warning, not customer complaints.

---

### Missing Piece 7 — Rules About How Long Data Is Kept
**The problem:** Right now there are no formal rules about how long emails, logs, and customer data are stored. In Europe, this is a legal requirement (GDPR).

**What we need to add:**
- Clear rules: raw emails deleted after 90 days, audit logs kept for 1 year, customer memory expires automatically
- A way to delete all data for a specific customer if they request it (GDPR right to erasure)
- A way to export a customer's data if they ask for it
- Written policy that can be shown to regulators

**Why companies care:** In France and Europe, this is the law. Without it, the product cannot be legally deployed.

---

### Missing Piece 8 — Different Systems Speak the Same Language
**The problem:** When we connect to different companies' ERP systems (SAP, Oracle, Salesforce, etc.), they all use different names for the same things. "Order number" in SAP might be called "transaction reference" in Oracle. This causes confusion.

**What we need to add:**
- A standard internal dictionary: every "order" is an Order, every "invoice" is an Invoice, no matter where the data comes from
- Translation layer that converts each company's ERP language into our standard language
- Detection system that raises an alarm when two sources disagree about the same fact

**Why companies care:** Without this, adding a second or third company becomes very complicated very quickly.

---

### Missing Piece 9 — Rules for When the AI Can Actually Change Things in the ERP
**The problem:** Right now the AI can read ERP data. But what about writing back — issuing a refund, cancelling an order, updating a shipment? This is much more serious and needs formal rules.

**What we need to add:**
- A list of every possible action, with a risk level: "safe to do automatically" vs "needs a human to approve" vs "never allowed"
- For any action that changes data: a human must approve before it executes
- A receipt for every change made, so it can be traced and reversed if needed
- A way to undo an action if a mistake was made

**Why companies care:** If the AI accidentally issues 500 refunds, someone needs to be able to stop it and reverse it.

---

### Missing Piece 10 — An Emergency Stop Button
**The problem:** What happens if the AI starts behaving badly? If the company providing the AI has an outage? If a bad update is pushed? Right now there's no emergency stop.

**What we need to add:**
- One button that switches the entire system from "send automatically" to "send nothing without human approval"
- Per-company version of the same button
- If the AI provider is down, automatically switch to a backup or send the pre-written safe emails
- A simple playbook for what to do in different emergency scenarios

**Why companies care:** Every serious enterprise product has a kill switch. Without one, IT security teams won't approve the deployment.

---

### Missing Piece 11 — A Proper Release Process
**The problem:** Right now, updates can be applied directly. For an enterprise product, that's too risky.

**What we need to add:**
- A test environment that looks exactly like the live environment
- Roll out updates to one company first, watch for problems, then roll out to everyone
- If a new version of the AI instructions makes responses worse, roll back to the previous version in one click
- A checklist that must be completed before any update goes live
- Automatic check that all settings are correct before the system starts

**Why companies care:** If an update breaks the product for all customers at once, that's a serious incident. Controlled rollouts prevent this.

---

### Missing Piece 12 — Knowing What It Costs
**The problem:** Every AI response costs money (OpenAI charges per word). Right now there's no way to know how much each company is costing or how to control it.

**What we need to add:**
- Track cost per ticket, per company, per day
- Show each company their own cost dashboard
- Route simple tickets to a cheaper AI model, complex tickets to a more expensive one (saves money automatically)
- Set a spending limit per company — send an alert when it's getting close
- Give companies a monthly cost report

**Why companies care:** They need to predict their costs. "It depends" is not an acceptable answer when budgeting.

---

### Missing Piece 13 — The AI Can Read Attachments
**The problem:** In B2B customer service, customers often attach PDFs, photos, invoices, and purchase orders. Right now the system ignores attachments completely.

**What we need to add:**
- Detect what type of file was attached
- Extract key information from PDFs and documents (order number, amounts, dates)
- Mark extracted information as "unverified" until confirmed against ERP data
- If the attachment is unreadable, send it to a human reviewer

**Why companies care:** A customer service system that can't handle attachments is missing a core part of real-world B2B support.

---

### Missing Piece 14 — Better Rules for Knowledge Articles
**The problem:** The system uses a knowledge base to answer questions. Right now there are no rules about keeping those articles fresh and accurate.

**What we need to add:**
- Each article has a version history (who changed it and when)
- Articles that haven't been updated in a long time get flagged as possibly outdated
- Each article has an owner — one person responsible for keeping it current
- Alert when an article says something that contradicts what the ERP data shows

**Why companies care:** Old or wrong knowledge base articles lead to wrong customer responses. That creates complaints and liability.

---

### Missing Piece 15 — Proper Multilingual Support
**The problem:** French and English work, but what about Dutch, Spanish, German, Italian? And even within French, a customer in Belgium expects different regulatory wording than one in France.

**What we need to add:**
- If the system is not confident about what language the customer is writing in, send it to a human instead of guessing
- Templates that format dates and numbers correctly by country
- Legal wording that changes by country (refund rights, delivery guarantees)
- Each company can define their preferred tone (formal vs friendly) and vocabulary

**Why companies care:** One wrong legal statement in a customer email can create a serious problem.

---

### Missing Piece 16 — Tools That Make Reviewers' Lives Easy
**The problem:** Supervisors who review AI responses need practical tools, not just the raw draft.

**What we need to add:**
- Filter tickets by urgency, company, type of request, or how long they've been waiting
- Add internal notes to a ticket that other reviewers can see
- Reassign a ticket to a colleague with one click
- See exactly why the AI was blocked ("it used an unverified delivery date")
- See exactly which facts and knowledge articles the AI used to write the draft
- Download a full history of any ticket for legal or compliance purposes

**Why companies care:** If the review console is clunky, reviewers work slowly and make mistakes. Good tooling is what makes human oversight actually work in practice.

---

## The Plan — Three Waves

### Before We Start (Next 4 Weeks)
*Just cleaning up and connecting real data. Not building anything new.*

- Week 1: Run all automated tests, fix any failures
- Week 1: Run quality check with test customer emails
- Week 2: Send one real customer email through the whole system and check the result
- Week 2: Connect to the real ERP system (replace test data with real data)
- Week 3: Set up automatic quality gate (blocks bad code from being applied)
- Week 3: Improve the AI instructions based on what we saw in the real test
- Week 4: Add real customer emails from our actual business into the test suite

---

### Wave 1 — The Keys to the Front Door (Weeks 5–12)
*Without this, no company will sign. This is the minimum viable enterprise product.*

**Weeks 5–6:** Who can do what (login, permissions, approval rules, approval log)

**Weeks 6–7:** Each company's data is completely separate

**Weeks 7–8:** Passwords and keys stored safely, three separate environments

**Weeks 8–10:** Review screen for human supervisors

**Weeks 10–12:** Live dashboard so ops team can see what's happening

**When Wave 1 is done:**
A company's IT team can audit it. Their compliance team can accept it. Their supervisors can do their job. The ops team can see if something is wrong.

---

### Wave 2 — Making It Safe to Operate (Weeks 13–18)
*This is what makes it legally deployable in Europe and operationally safe for enterprises.*

**Weeks 13–14:** Data retention rules and customer data deletion (GDPR)

**Weeks 14–15:** Rules for when the AI can change ERP data (with human approval required)

**Weeks 15–16:** Emergency stop button and safe shutdown modes

**Weeks 16–17:** Proper release process — test first, roll out slowly, roll back if needed

**Weeks 17–18:** Each ERP speaks the same language internally

**Weeks 17–18:** Watch live quality and send alerts when something is drifting

**When Wave 2 is done:**
The product can pass a GDPR audit. An incident can be handled without an engineer. A bad update can be reversed in minutes. The ops team gets automatic warnings instead of finding out from customers.

---

### Wave 3 — Growing the Market (Weeks 19–24)
*This widens what types of companies can use the product and deepens the competitive advantage.*

**Weeks 19–20:** The AI can read and understand PDF attachments and invoices

**Weeks 20–21:** Knowledge base articles are versioned, owned, and kept fresh

**Weeks 21–22:** Better language and locale handling for more countries

**Weeks 22–23:** Cost tracking and spending controls per company

**Weeks 23–24:** Better supervisor tools — filters, notes, reassignment, audit export

**When Wave 3 is done:**
The product handles real B2B workloads. Companies can manage their own settings without needing us. The product can be sold to any European B2B company without custom work for each one.

---

## The Four Finish Lines

**Finish Line 1 — Engine Verified** *(End of pre-launch)*
All tests pass. Quality score above 80%. Real orders flowing through. Automatic quality gate active.

**Finish Line 2 — First Enterprise Customer** *(End of Wave 1)*
A real company can be onboarded. Their IT team is satisfied. Their supervisors have a console. Their data is isolated. Their ops team has a dashboard.

**Finish Line 3 — Legally Deployable in Europe** *(End of Wave 2)*
Can pass a CNIL or GDPR audit. Incidents are manageable. Releases are controlled. Quality is monitored automatically.

**Finish Line 4 — Ready to Sell to Anyone** *(End of Wave 3)*
Handles attachments, multiple languages, multiple ERP systems. Companies manage themselves. Costs are predictable. Supervisors have everything they need.

---

## One Sentence Summary

We built the smartest engine in the garage. The next 6 months is about building the car around it — the seats, the dashboard, the doors, the license plate — so that companies feel safe enough to actually drive it.

---

*April 2026 — Based on the CS AI engine build and enterprise AI guidance from OpenAI, Anthropic, McKinsey, CNIL, and OWASP.*
