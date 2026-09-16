#!/usr/bin/env python3
"""CLI: run the one-shot web research step for a game and fold the result
into the `game_research` sqlite table (see GameResearchRepository).

Usage: python scripts/research.py <game_id>
"""
import sys

from roleplay_agent.api.dependencies import get_researcher


def main() -> None:
    if len(sys.argv) != 2:
        print("Usage: python scripts/research.py <game_id>")
        sys.exit(1)
    notes = get_researcher().research(sys.argv[1])
    print(notes)


if __name__ == "__main__":
    main()
