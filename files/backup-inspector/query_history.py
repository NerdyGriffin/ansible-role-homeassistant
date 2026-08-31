#!/usr/bin/env python3
"""Report entity history from a Home Assistant recorder database.

Intended for a ``home-assistant_v2.db`` recovered from a backup, so it opens
the file read-only and immutable: the database is never written to, and a
missing write-ahead log does not matter.

A recorder database only holds rows for state *changes*, so a single row over
a long window means the entity held that value throughout, and a value
repeated after an ``unavailable`` row is a restart rather than a real change.
"""

from __future__ import annotations

import argparse
import datetime as dt
import sqlite3
import sys


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--db", required=True, help="path to home-assistant_v2.db")
    parser.add_argument(
        "--entity-pattern",
        default="%",
        help="SQL LIKE pattern matched against entity_id (default: %%)",
    )
    parser.add_argument(
        "--transitions-only",
        action="store_true",
        help="print only rows whose value differs from the previous row",
    )
    parser.add_argument(
        "--max-rows",
        type=int,
        default=40,
        help="cap the rows printed per entity (default: 40)",
    )
    return parser.parse_args()


def local(ts: float | None) -> str:
    if ts is None:
        return "n/a"
    moment = dt.datetime.fromtimestamp(ts, dt.timezone.utc).astimezone()
    return moment.strftime("%Y-%m-%d %H:%M:%S")


def main() -> int:
    args = parse_args()
    connection = sqlite3.connect(f"file:{args.db}?mode=ro&immutable=1", uri=True)
    cursor = connection.cursor()

    cursor.execute("SELECT MIN(last_updated_ts), MAX(last_updated_ts) FROM states")
    first, last = cursor.fetchone()
    print(f"recorder window: {local(first)}  ->  {local(last)}")

    cursor.execute(
        "SELECT metadata_id, entity_id FROM states_meta "
        "WHERE entity_id LIKE ? ORDER BY entity_id",
        (args.entity_pattern,),
    )
    entities = cursor.fetchall()
    if not entities:
        print(f"no entity matched {args.entity_pattern!r}")
        return 1

    for metadata_id, entity_id in entities:
        cursor.execute(
            "SELECT last_updated_ts, state FROM states "
            "WHERE metadata_id=? ORDER BY last_updated_ts",
            (metadata_id,),
        )
        rows = cursor.fetchall()
        values = sorted({state for _, state in rows})
        print(f"\n{entity_id}\n  rows={len(rows)}  values={values}")

        shown = 0
        previous = None
        for timestamp, state in rows:
            if args.transitions_only and state == previous:
                previous = state
                continue
            previous = state
            if shown >= args.max_rows:
                print(f"  ... {len(rows) - shown} more")
                break
            print(f"  {local(timestamp)}  -> {state}")
            shown += 1

    connection.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
