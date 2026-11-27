"""Run every query in queries/**/*.cypher against Neo4j and report rows and time.

    uv run cg-check-queries [--dir queries] [--timeout 120]

A query fails on an error or when it returns no rows (its example values on the first WITH line
no longer match the graph). Exit 1 if any query fails. Read-only: queries run in read
transactions, so a query that tries to write is rejected by the database.
"""

from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from neo4j import READ_ACCESS, GraphDatabase, Query

from .cli import DEFAULT_ENV, DEFAULT_URI, _password


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--dir", default=str(Path(__file__).resolve().parents[4] / "queries"))
    ap.add_argument("--uri", default=DEFAULT_URI)
    ap.add_argument("--db", default="neo4j")
    ap.add_argument("--auth-env", default=DEFAULT_ENV)
    ap.add_argument("--timeout", type=float, default=120, help="seconds per query")
    a = ap.parse_args(argv)

    files = sorted(Path(a.dir).rglob("*.cypher"))
    if not files:
        sys.exit(f"no .cypher files under {a.dir}")
    failed = 0
    with GraphDatabase.driver(a.uri, auth=_password(a.auth_env)) as driver:
        with driver.session(database=a.db, default_access_mode=READ_ACCESS) as s:
            for f in files:
                text = f.read_text()
                title = text.splitlines()[0].lstrip("/ ").strip()
                t = time.time()
                try:
                    rows = s.run(Query(text, timeout=a.timeout)).data()
                    status = "ok  " if rows else "EMPTY"
                    failed += not rows
                    detail = f"{len(rows):>4} rows"
                except Exception as exc:  # report and continue
                    status, detail = "ERR ", f"{type(exc).__name__}: {str(exc)[:120]}"
                    failed += 1
                el = time.time() - t
                print(f"{status} {el:6.1f}s  {f.relative_to(a.dir)}  {detail}  ({title})")
    print(f"{len(files) - failed}/{len(files)} queries ok")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
