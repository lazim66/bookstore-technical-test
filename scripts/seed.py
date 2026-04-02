"""Standalone seed script — run without restarting the API.

Requires the API to have started at least once (to create DB tables).
If tables don't exist yet, run `just start` first.

Usage:
    just seed
    # or: docker compose exec api python scripts/seed.py
"""

import asyncio

from src.utils.seed import run_all_seeds


async def main() -> None:
    print("Running seeds...")
    await run_all_seeds()
    print("Seeding complete.")


if __name__ == "__main__":
    asyncio.run(main())
