# 11 — Channels: Email Noise Filtering

## What This Does

Even after the NLP noise filter (Prompt 01) catches obvious auto-replies,
there are email-level problems that need to be handled at the channel layer
before a message even reaches the NLP pipeline:

- **Mailer loops:** A customer sends "Re: Re: Re: Re:" chains that quote
  the entire thread history. The AI only needs to see the new content.
- **Known noise senders:** Emails from `mailer-daemon@`, `noreply@`,
  `postmaster@` should never become tickets.
- **Quoted reply chains:** Every reply email includes the previous messages
  quoted below. Without stripping this, the AI reads the entire history
  as if it were the new message — confusing the NLP and wasting tokens.
- **Subject line clutter:** "Re: Re: Re: FWD: TR: Order 1003" should be
  cleaned to "Order 1003" for display and analysis.

This improvement adds filtering and cleaning directly to the email reader
in `channels.py` so that by the time a message reaches the pipeline, it
contains only clean, relevant content.

**Where the change lives:** `channels.py` only.

**Impact:** Cleaner NLP analysis, lower token costs, no tickets created
from delivery failures or mailer loops, agents see clean subject lines.

---

## Prompt — Paste into Claude Code

```
Add noise filtering and content cleaning to the EmailReader in channels.py.

TASK:

1. Add is_noise_email(msg: InboundMessage) -> tuple[bool, str] to EmailReader:
   Returns (True, reason) for:
   - Sender matches: "mailer-daemon@", "postmaster@", "noreply@",
     "no-reply@", "donotreply@" (case-insensitive, substring match)
   - Subject has more than 2 "Re:" prefixes (loop risk)
   - Body is empty after stripping whitespace and HTML tags
   Returns (False, "") otherwise.

2. Add clean_subject(subject: str) -> str:
   Strips leading prefixes: "Re:", "Fwd:", "FW:", "TR:", "Rép:", "Réf:"
   (case-insensitive, repeated). Strips extra whitespace.
   Example: "Re: Re: FW:  Order 1003 " → "Order 1003"

3. Add clean_body(body: str) -> str:
   Strips the quoted reply chain — everything after the first line matching:
   - "On [date].*wrote:" (English)
   - "Le [date].*a écrit" (French)
   - "-----Original Message-----"
   - "________________________________"
   - "De :" / "From :" at the start of a line (common in Outlook forwards)
   Returns only the new content the customer actually wrote.
   If nothing to strip, returns body unchanged.

4. In fetch_new():
   - Call is_noise_email() on each message — if noise, skip it entirely
     and append to a skip log: cs_ai/data/{company}/email_skip_log.json
     with {timestamp, sender, subject, reason}
   - Call clean_subject() on every message's subject before returning
   - Call clean_body() on every message's body before returning

Do NOT change nlp.py, main.py, connector.py, tickets.py, or JSON data files.
```
