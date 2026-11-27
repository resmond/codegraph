"""git history extractor: per-file churn and authors, and co-change pairs.

    uv run cg-extract-git --out ~/.cache/codegraph/runs/<run> [--since 2015-01-01]

Co-change counts pairs of files changed in the same commit, ignoring merges and commits
touching more than --max-files files (mass reformatting, moves).
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from collections import Counter, defaultdict
from itertools import combinations
from pathlib import Path

from codegraph_schema import SCHEMA_VERSION, JsonlWriter

CODE_SUFFIXES = (".cpp", ".cxx", ".h", ".hpp", ".py", ".pyi", ".ui", ".xml")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--freecad", default=str(Path.home() / "src/FreeCAD"))
    ap.add_argument("--out", required=True)
    ap.add_argument("--since", default="", help="e.g. 2015-01-01 (default: all history)")
    ap.add_argument("--max-files", type=int, default=30)
    ap.add_argument("--min-pair", type=int, default=3)
    a = ap.parse_args(argv)
    freecad, out = Path(a.freecad), Path(a.out).expanduser()

    cmd = [
        "git",
        "-C",
        str(freecad),
        "log",
        "--no-merges",
        "--numstat",
        "--no-renames",
        "--format=@@%H\t%at\t%aN",
        "--",
        "src",
    ]
    if a.since:
        cmd.insert(4, f"--since={a.since}")
    proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, text=True, errors="replace")

    commits = Counter()
    added = Counter()
    deleted = Counter()
    first: dict[str, int] = {}
    last: dict[str, int] = {}
    authors: dict[str, Counter] = defaultdict(Counter)
    pairs = Counter()
    n_commits = 0

    def flush(ts: int, author: str, files: list[str]) -> None:
        for f in files:
            commits[f] += 1
            authors[f][author] += 1
            first[f] = min(first.get(f, ts), ts)
            last[f] = max(last.get(f, ts), ts)
        if 1 < len(files) <= a.max_files:
            for p in combinations(sorted(files), 2):
                pairs[p] += 1

    cur: tuple[int, str] | None = None
    files: list[str] = []
    assert proc.stdout is not None
    for line in proc.stdout:
        line = line.rstrip("\n")
        if line.startswith("@@"):
            if cur:
                flush(*cur, files)
            _, ts, author = line[2:].split("\t", 2)
            cur, files = (int(ts), author), []
            n_commits += 1
        elif line:
            parts = line.split("\t")
            if len(parts) == 3 and parts[2].endswith(CODE_SUFFIXES):
                ad, de, path = parts
                files.append(path)
                added[path] += int(ad) if ad.isdigit() else 0
                deleted[path] += int(de) if de.isdigit() else 0
    if cur:
        flush(*cur, files)
    proc.wait()

    with JsonlWriter(out / "git.jsonl") as w:
        w.write(
            {
                "t": "run",
                "tool": "extract-git",
                "schema": SCHEMA_VERSION,
                "commits": n_commits,
                "since": a.since or "all",
            }
        )
        for f, n in commits.items():
            w.write(
                {
                    "t": "churn",
                    "file": f,
                    "commits": n,
                    "added": added[f],
                    "deleted": deleted[f],
                    "first": first[f],
                    "last": last[f],
                    "authors": len(authors[f]),
                    "top_authors": [x for x, _ in authors[f].most_common(3)],
                }
            )
        for (x, y), n in pairs.items():
            if n >= a.min_pair:
                w.write({"t": "cochange", "a": x, "b": y, "n": n})
    print(f"git: {n_commits} commits, {len(commits)} files, {w.count} records -> {w.path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
