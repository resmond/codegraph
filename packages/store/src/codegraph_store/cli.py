"""Load a fact run into codegraph's Neo4j (replaces all fact data; annotations are kept).

    uv run cg-load --run ~/.cache/codegraph/runs/<run> --dry-run   build + counts, no database
    uv run cg-load --run ~/.cache/codegraph/runs/<run>             wipe facts, load, verify

Password: $NEO4J_PASSWORD if set, else read over SSH from the server's compose .env
(NEO4J_AUTH=neo4j/<password>, created by ~/configs/homelab/scripts/deploy-codegraph.sh).
It is held in memory only and never printed or written.
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import time
from pathlib import Path

from .model import build_graph

DEFAULT_URI = "bolt://192.168.1.16:7687"  # amd-speech
DEFAULT_ENV = "amd-speech:/opt/codegraph/.env"


def _password(env_spec: str) -> tuple[str, str]:
    if os.environ.get("NEO4J_PASSWORD"):
        return os.environ.get("NEO4J_USER", "neo4j"), os.environ["NEO4J_PASSWORD"]
    host, path = env_spec.split(":", 1)
    out = subprocess.run(
        ["ssh", "-n", host, f"grep -m1 '^NEO4J_AUTH=' {path}"],
        capture_output=True,
        text=True,
    )
    line = out.stdout.strip()
    if out.returncode or "/" not in line:
        sys.exit(f"could not read NEO4J_AUTH from {env_spec} (ssh exit {out.returncode})")
    user, pw = line.split("=", 1)[1].split("/", 1)
    return user, pw


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--run", required=True, help="run directory with tus/, python.jsonl, git.jsonl")
    ap.add_argument("--uri", default=DEFAULT_URI)
    ap.add_argument("--db", default="neo4j")
    ap.add_argument("--auth-env", default=DEFAULT_ENV, help="host:path of the NEO4J_AUTH .env")
    ap.add_argument("--batch", type=int, default=5000)
    ap.add_argument("--dry-run", action="store_true", help="build the graph, print counts only")
    a = ap.parse_args(argv)

    t = time.time()
    g = build_graph(Path(a.run))
    rev = g.run["freecad_rev"]
    print(f"built graph from {g.run['id']} in {time.time() - t:.0f} s (FreeCAD {rev})")
    counts = g.counts()
    for k, v in counts.items():
        print(f"  {k:<22} {v:>9,}")
    if g.notes:
        print("notes: " + ", ".join(f"{k}={v:,}" for k, v in sorted(g.notes.items())))
    if a.dry_run:
        print("Dry run only - database not touched.")
        return 0

    from neo4j import GraphDatabase

    from .neo4j_load import load, verify

    user, pw = _password(a.auth_env)
    with GraphDatabase.driver(a.uri, auth=(user, pw)) as driver:
        driver.verify_connectivity()
        print(f"connected to {a.uri}; replacing fact data (annotations kept)")
        load(driver, g, db=a.db, batch=a.batch)
        got = verify(driver, a.db)
    print("verify (database):")
    for k, v in got.items():
        print(f"  {k:<22} {v:>9,}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
