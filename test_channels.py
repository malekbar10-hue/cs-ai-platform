"""
test_channels.py — Smoke test for the communication channel layer.

Actions:
  1. Load config from config.json
  2. Connect to IMAP inbox
  3. Fetch the 3 most recent emails (read OR unread)
  4. Print a preview of each message
  5. Disconnect cleanly

No emails are sent. No messages are marked as read.
Run with:  python test_channels.py
"""

import json
import os
import sys
from channels import get_channel_reader

CONFIG_PATH = os.path.join(os.path.dirname(__file__), "config.json")


def load_config() -> dict:
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def print_preview(idx: int, msg) -> None:
    separator = "-" * 60
    print(separator)
    print(f"[{idx}] Message ID : {msg.message_id}")
    print(f"     Channel    : {msg.channel}")
    print(f"     From       : {msg.sender_name} <{msg.sender}>")
    print(f"     To         : {', '.join(msg.recipients)}")
    print(f"     Subject    : {msg.subject}")
    print(f"     Date       : {msg.timestamp}")
    body_preview = msg.body[:200].replace("\n", " ").replace("\r", "")
    print(f"     Body (200c): {body_preview}{'...' if len(msg.body) > 200 else ''}")


def main():
    config = load_config()
    comm_cfg = config.get("communication")
    if not comm_cfg:
        print("[ERROR] No 'communication' block found in config.json.")
        print("        Add inbound IMAP credentials before running this test.")
        sys.exit(1)

    inbound_cfg = comm_cfg.get("inbound", {})
    host = inbound_cfg.get("host", "?")
    user = inbound_cfg.get("username", "?")
    mailbox = inbound_cfg.get("mailbox", "INBOX")

    print(f"Connecting to IMAP  : {host}")
    print(f"Account             : {user}")
    print(f"Mailbox             : {mailbox}")
    print()

    reader = get_channel_reader(comm_cfg)

    try:
        reader.connect()
        print("Connection OK — fetching 3 most recent messages...\n")

        messages = reader.fetch_recent(max_messages=3)

        if not messages:
            print("Inbox appears empty (or no messages matched).")
        else:
            print(f"Fetched {len(messages)} message(s):\n")
            for i, msg in enumerate(messages, start=1):
                print_preview(i, msg)

        print("-" * 60)
        print("Test complete. No messages were sent or marked as read.")

    except Exception as exc:
        print(f"\n[ERROR] {type(exc).__name__}: {exc}")
        print("\nCommon causes:")
        print("  - Wrong host / port in config.json")
        print("  - Wrong credentials (check password or app password)")
        print("  - IMAP not enabled for your email account")
        print("  - Firewall blocking outbound port 993")
        sys.exit(1)

    finally:
        reader.disconnect()


if __name__ == "__main__":
    main()
