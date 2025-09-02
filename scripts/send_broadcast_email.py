#!/usr/bin/env python3
# Created: 2025-09-02
# Author: SurgiCase Automation

"""
One-off broadcast email to all users in users_and_tiers.

Features:
- Personalizes greeting with first name ("Dear <first name>,")
- Sends via utils.email_service.send_email (SES backed)
- Batches sends to avoid rate limits
- --dry-run to preview without sending
- --limit to restrict recipients during testing
- --test-email to send only to a single address

Usage examples:
  python scripts/send_broadcast_email.py --dry-run
  python scripts/send_broadcast_email.py --limit 50 --batch-size 20
  python scripts/send_broadcast_email.py --test-email you@example.com --test-first-name You --send
  python scripts/send_broadcast_email.py --send
"""

import argparse
import sys
import time
import os
from typing import List, Dict

# Ensure project root is on sys.path when running as a script
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(CURRENT_DIR)
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from core.database import get_db_connection, close_db_connection
from utils.email_service import send_email


EMAIL_SUBJECT = "SurgiCase: Document Quality Tips"

EMAIL_BODY_TEMPLATE = (
    "Dear {first_name},\n\n"
    "We have been reviewing case documents in SurgiCase.  We have come across 2 issues so far.\n\n"
    "1. We would like you to make sure if you have multiple pages in your face sheet due to extra information etc, that you please place the actual face sheet/demographic sheet as the first page.  For some future enhancements, this will be critical.\n\n"
    "2. If you fold your documents to put them in your pocket or bag, please do your best to smooth them out before you take pictures of them.  When they are bent due to the folds, it makes them harder for the computer to read.\n\n"
    "Thank you,\n"
    "SurgiCase Administrators\n\n"
)


def fetch_recipients(limit: int = 0) -> List[Dict[str, str]]:
    """Fetch first_name and user_email from users_and_tiers."""
    conn = None
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        sql = (
            "SELECT first_name, user_email "
            "FROM users_and_tiers "
            "WHERE user_email IS NOT NULL AND user_email != ''"
        )
        if limit and limit > 0:
            sql += " LIMIT %s"
            cursor.execute(sql, (limit,))
        else:
            cursor.execute(sql)
        rows = cursor.fetchall() or []
        recipients: List[Dict[str, str]] = []
        for row in rows:
            first_name = (row.get("first_name") or "").strip()
            email = (row.get("user_email") or "").strip()
            if not email:
                continue
            recipients.append({"first_name": first_name or "there", "email": email})
        return recipients
    finally:
        if conn:
            close_db_connection(conn)


def chunk_list(items: List[Dict[str, str]], chunk_size: int) -> List[List[Dict[str, str]]]:
    return [items[i:i + chunk_size] for i in range(0, len(items), chunk_size)]


def build_body(first_name: str) -> str:
    return EMAIL_BODY_TEMPLATE.format(first_name=first_name or "there")


def send_batch(recipients: List[Dict[str, str]], dry_run: bool) -> int:
    sent = 0
    for r in recipients:
        to_address = r["email"]
        first_name = r.get("first_name") or "there"
        body = build_body(first_name)
        if dry_run:
            print(f"[DRY-RUN] Would send to {to_address} with greeting 'Dear {first_name},'")
            sent += 1
            continue
        result = send_email(
            to_addresses=to_address,
            subject=EMAIL_SUBJECT,
            body=body,
            email_type="broadcast_notice"
        )
        if result.get("success"):
            sent += 1
        else:
            err = result.get("error") or "unknown error"
            print(f"[ERROR] Failed to send to {to_address}: {err}", file=sys.stderr)
    return sent


def main():
    parser = argparse.ArgumentParser(description="Send a one-off broadcast email to all users.")
    group = parser.add_mutually_exclusive_group(required=False)
    group.add_argument("--dry-run", action="store_true", help="Preview recipients without sending")
    group.add_argument("--send", action="store_true", help="Actually send the emails")
    parser.add_argument("--limit", type=int, default=0, help="Limit number of recipients for testing")
    parser.add_argument("--batch-size", type=int, default=25, help="Emails to send per batch")
    parser.add_argument("--sleep", type=float, default=1.0, help="Seconds to sleep between batches")
    parser.add_argument("--test-email", type=str, default=None, help="Send only to this email address (no DB scan)")
    parser.add_argument("--test-first-name", type=str, default=None, help="Optional first name for test email greeting")

    args = parser.parse_args()

    dry_run = args.dry_run or not args.send

    if args.test_email:
        recipients = [{
            "first_name": (args.test_first_name or "there").strip(),
            "email": args.test_email.strip(),
        }]
    else:
        recipients = fetch_recipients(limit=args.limit)
    if not recipients:
        print("No recipients found.")
        return 0

    total = 0
    batches = chunk_list(recipients, args.batch_size)
    for idx, batch in enumerate(batches, start=1):
        print(f"Processing batch {idx}/{len(batches)} (size={len(batch)})...")
        total += send_batch(batch, dry_run=dry_run)
        if idx < len(batches) and not dry_run and args.sleep > 0:
            time.sleep(args.sleep)

    mode = "DRY-RUN" if dry_run else "SENT"
    print(f"{mode}: {total} emails processed.")
    return 0


if __name__ == "__main__":
    sys.exit(main())


