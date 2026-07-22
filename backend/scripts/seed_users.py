"""Seed (upsert) a dashboard user. Passwords never touch argv or the repo.

Usage (from backend/):
    uv run python scripts/seed_users.py <username> <ADMIN|SENIOR_AUDITOR|AUDITOR> \
        --display-name "ชื่อที่แสดง"

The password is prompted interactively (or read from SEED_PASSWORD for
scripted setup). Re-running with an existing username updates the password,
role, and display name.
"""

from __future__ import annotations

import argparse
import getpass
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from sqlalchemy import create_engine, text  # noqa: E402

from app.core.security import Role, hash_password  # noqa: E402
from app.core.settings import get_settings  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("username")
    parser.add_argument("role", choices=[r.value for r in Role])
    parser.add_argument("--display-name", default=None, help="Thai display name")
    args = parser.parse_args()

    password = os.environ.get("SEED_PASSWORD") or getpass.getpass(f"Password for {args.username}: ")
    if not password:
        parser.error("empty password")

    engine = create_engine(get_settings().database_url)
    with engine.begin() as conn:
        conn.execute(
            text(
                """
                INSERT INTO users (username, password_hash, display_name_th, role)
                VALUES (:username, :password_hash, :display_name_th, :role)
                ON CONFLICT (username) DO UPDATE SET
                    password_hash = EXCLUDED.password_hash,
                    display_name_th = EXCLUDED.display_name_th,
                    role = EXCLUDED.role,
                    is_active = TRUE
                """
            ),
            {
                "username": args.username,
                "password_hash": hash_password(password),
                "display_name_th": args.display_name or args.username,
                "role": args.role,
            },
        )
    print(f"user {args.username!r} seeded with role {args.role}")


if __name__ == "__main__":
    main()
