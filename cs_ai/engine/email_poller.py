"""
email_poller.py — Background IMAP polling script.

Run with:  python email_poller.py

Every N seconds (config["communication"]["polling_interval_seconds"]):
  1. Fetch unread emails from the configured inbox
  2. For each email:
     - If a matching open ticket exists (by thread_id) → append message
     - Otherwise → create a new ticket + run initial NLP tagging
  3. Mark processed emails as read

Does NOT send anything. Does NOT touch main.py, connector.py, or nlp.py directly
beyond the standard imports used by the rest of the platform.
"""

from __future__ import annotations

import json
import os
import sys
import time
from datetime import datetime, UTC
from paths import config_path as _config_path

def _now() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)

# ---------------------------------------------------------------------------
# Load config early so we can fail fast if it's missing
# ---------------------------------------------------------------------------

def _load_config() -> dict:
    with open(_config_path(), "r", encoding="utf-8") as f:
        return json.load(f)

CONFIG = _load_config()

# ---------------------------------------------------------------------------
# Imports (after config so we get clean error messages)
# ---------------------------------------------------------------------------

from channels import get_channel_reader, InboundMessage
from tickets  import TicketManager, Ticket

# NLP imports — same functions used by app.py and app_inbox.py
from main import (
    detect_language,
    detect_emotion,
    detect_intent,
    detect_topic,
    find_order,
)

# ---------------------------------------------------------------------------
# Config helpers
# ---------------------------------------------------------------------------

def _poll_interval() -> int:
    """Return polling interval in seconds from config, default 60."""
    comm = CONFIG.get("communication", {})
    return int(comm.get("polling_interval_seconds", 60))


def _comm_cfg() -> dict:
    return CONFIG.get("communication", {})


# ---------------------------------------------------------------------------
# Initial NLP analysis for a newly created ticket
# ---------------------------------------------------------------------------

def _run_initial_analysis(ticket: Ticket, tm: TicketManager) -> None:
    """
    Tag a brand-new ticket with language, emotion, intent, topic, and order_id
    based on the first customer message.
    This is a lightweight pass — no AI draft is generated here.
    That happens interactively in app_inbox.py when an agent opens the ticket.
    """
    if not ticket.messages:
        return

    first_msg = ticket.messages[0].get("content", "")
    if not first_msg.strip():
        return

    text = first_msg.lower()

    try:
        language, _, _                            = detect_language(text)
        emotion, intensity, all_scores, emo_conf  = detect_emotion(text)
        intent, int_conf                          = detect_intent(text)
        topic,  top_conf                          = detect_topic(text)
        order_info, priority, order_id            = find_order(first_msg)

        updates = {
            "emotion":  emotion,
            "intent":   intent,
            "status":   "triaged",
        }
        if order_id:
            updates["order_id"] = order_id
            updates["priority"] = priority

        tm.update_ticket(ticket.ticket_id, **updates)

        print(
            f"  [NLP]  emotion={emotion} ({intensity})  "
            f"intent={intent}  lang={language}"
            + (f"  order={order_id}" if order_id else "")
        )

    except Exception as exc:
        print(f"  [NLP]  Warning: initial analysis failed — {exc}")


# ---------------------------------------------------------------------------
# Thread ID extraction from raw email
# ---------------------------------------------------------------------------

def _extract_thread_id(msg: InboundMessage) -> str:
    """
    Derive the thread_id from the email headers.

    Logic:
      1. Use the first message-id in the References header (original thread root)
      2. Fall back to In-Reply-To header
      3. Fall back to the message's own message_id (this IS the root)
    """
    raw = msg.raw
    if raw is None:
        return msg.message_id

    references = raw.get("References", "").strip()
    if references:
        # References is a space-separated list; first entry = thread root
        return references.split()[0].strip("<>")

    in_reply_to = raw.get("In-Reply-To", "").strip().strip("<>")
    if in_reply_to:
        return in_reply_to

    return msg.message_id


# ---------------------------------------------------------------------------
# Process one inbound message
# ---------------------------------------------------------------------------

def process_message(msg: InboundMessage, tm: TicketManager) -> str:
    """
    Route an inbound message to an existing ticket or create a new one.
    Returns "appended" or "created".
    """
    thread_id = _extract_thread_id(msg)

    existing = tm.find_by_thread(thread_id)

    if existing:
        # Append to existing thread
        tm.add_message(
            existing.ticket_id,
            {
                "role":      "customer",
                "content":   msg.body,
                "timestamp": msg.timestamp.isoformat(),
            },
        )
        # Re-open if it was in a terminal state
        if existing.status in ("sent", "resolved"):
            tm.update_ticket(existing.ticket_id, status="new")

        print(
            f"  [APPEND] ticket={existing.ticket_id[:8]}  "
            f"subject='{existing.subject[:40]}'"
        )
        return "appended"

    else:
        # Create brand-new ticket
        new_ticket = tm.create_ticket(
            inbound_message=msg,
            thread_id=thread_id,
        )
        print(
            f"  [NEW]    ticket={new_ticket.ticket_id[:8]}  "
            f"from={msg.sender}  subject='{msg.subject[:40]}'"
        )
        _run_initial_analysis(new_ticket, tm)
        return "created"


# ---------------------------------------------------------------------------
# Single poll cycle
# ---------------------------------------------------------------------------

def poll_once(tm: TicketManager) -> tuple[int, int]:
    """
    Connect to IMAP, fetch unread messages, process each, mark as read.
    Returns (created_count, appended_count).
    """
    comm = _comm_cfg()
    if not comm:
        print("[POLLER] No 'communication' block in config.json — nothing to poll.")
        return 0, 0

    created  = 0
    appended = 0

    reader = get_channel_reader(comm)
    try:
        reader.connect()
        messages = reader.fetch_unread(max_messages=50)

        if not messages:
            print("  [POLLER] No new messages.")
            return 0, 0

        print(f"  [POLLER] {len(messages)} unread message(s) found.")

        for msg in messages:
            result = process_message(msg, tm)
            if result == "created":
                created  += 1
            else:
                appended += 1
            # Mark as read so we don't process it again next cycle
            try:
                reader.mark_read(msg.message_id)
            except Exception as e:
                print(f"  [WARN] Could not mark message {msg.message_id} as read: {e}")

    except Exception as exc:
        print(f"[POLLER] Connection error: {type(exc).__name__}: {exc}")
        print("         Check your IMAP credentials and host in config.json.")
    finally:
        reader.disconnect()

    return created, appended


# ---------------------------------------------------------------------------
# Main loop
# ---------------------------------------------------------------------------

def run_poller() -> None:
    interval = _poll_interval()
    tm = TicketManager()

    print(f"[POLLER] Starting — polling every {interval}s")
    print(f"[POLLER] IMAP host: {_comm_cfg().get('inbound', {}).get('host', 'not configured')}")
    print(f"[POLLER] Tickets DB: {tm._db_path}")
    print("[POLLER] Press Ctrl+C to stop.\n")

    cycle = 0
    while True:
        cycle += 1
        ts = _now().strftime("%Y-%m-%d %H:%M:%S UTC")
        print(f"[{ts}] Cycle #{cycle}")

        closed = tm.auto_close_stale()
        if closed:
            print(f"  [AUTO-CLOSE] Closed {closed} stale ticket(s).")

        created, appended = poll_once(tm)
        if created or appended:
            print(f"  => Created: {created}  Appended: {appended}")

        print(f"  => Sleeping {interval}s…\n")
        try:
            time.sleep(interval)
        except KeyboardInterrupt:
            print("\n[POLLER] Stopped by user.")
            sys.exit(0)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    try:
        run_poller()
    except KeyboardInterrupt:
        print("\n[POLLER] Stopped.")
        sys.exit(0)
