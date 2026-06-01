#!/usr/bin/env python3
"""Generate a Telethon StringSession for a USER account (live Telegram search).

Run this ONCE, locally and interactively. It prints a session string that you
then store as the Sinas secret TELEGRAM_SESSION_STRING (never commit it).

A user account is required because channels.searchPosts is user-only (bots
cannot do global search). Treat the session string like full account access:
anyone with it can act as your account.

Usage:
    export TELEGRAM_API_ID=...        # from my.telegram.org
    export TELEGRAM_API_HASH=...
    uv run python scripts/bootstrap_telegram_session.py

You will be prompted for your phone number, the login code Telegram sends, and
your 2FA password if set.
"""

from __future__ import annotations

import os
import sys


def main() -> int:
    api_id = os.environ.get("TELEGRAM_API_ID")
    api_hash = os.environ.get("TELEGRAM_API_HASH")
    if not api_id or not api_hash:
        print("ERROR: set TELEGRAM_API_ID and TELEGRAM_API_HASH env vars first.",
              file=sys.stderr)
        print("Get them from https://my.telegram.org -> API development tools.",
              file=sys.stderr)
        return 2

    try:
        from telethon.sync import TelegramClient
        from telethon.sessions import StringSession
    except Exception as exc:  # pragma: no cover
        print(f"ERROR: telethon not installed ({exc!r}). "
              "Install with: uv pip install telethon", file=sys.stderr)
        return 3

    print("Starting interactive login (you'll be asked for phone + code)...")
    with TelegramClient(StringSession(), int(api_id), api_hash) as client:
        session_string = client.session.save()

    print("\n=== TELEGRAM_SESSION_STRING (store as a Sinas secret; DO NOT COMMIT) ===")
    print(session_string)
    print("=== end ===")
    print("\nNext: set it as a Sinas secret (TELEGRAM_SESSION_STRING) and enable "
          "ENABLE_TELEGRAM_LIVE_SEARCH=true on the clip2trace package.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
