#!/usr/bin/env python3
"""Maintenance: VACUUM the sqlite db."""
import sqlite3

from roleplay_agent.config.settings import get_settings


def main() -> None:
    settings = get_settings()

    if settings.db_path.exists():
        conn = sqlite3.connect(settings.db_path)
        conn.execute("VACUUM")
        conn.close()
        print(f"vacuumed {settings.db_path}")


if __name__ == "__main__":
    main()
