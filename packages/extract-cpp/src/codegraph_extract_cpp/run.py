"""Parallel, resumable runner: one JSONL file per translation unit.

    uv run cg-extract-cpp --out ~/.cache/codegraph/runs/<run> --workers 6 [--limit N] [--match S]

Re-running with the same --out skips TUs whose output file already exists, so an interrupted
run resumes where it stopped. Progress goes to <out>/progress.log; failures to failures.jsonl.
"""

from __future__ import annotations

import argparse
import hashlib
import json
import multiprocessing as mp
import os
import subprocess
import sys
import time
import traceback
from datetime import UTC, datetime
from pathlib import Path

from codegraph_schema import SCHEMA_VERSION, dumps

from .toolchain import Toolchain, load_compile_db

_W: dict = {}


def _out_name(tc: Toolchain, file: str) -> str:
    rel = tc.rel(file)
    h = hashlib.sha1(rel.encode()).hexdigest()[:10]
    return f"{rel.replace('/', '__')}.{h}.jsonl"


def _init_worker(freecad: str, build: str) -> None:
    import clang.cindex as ci

    from .extract import TuExtractor

    tc = Toolchain(Path(freecad), Path(build))
    ci.Config.set_library_file(str(tc.libclang))
    _W["tc"] = tc
    _W["ex"] = TuExtractor(tc, ci.Index.create(), tc.base_args())


def _work(job: tuple[dict, str]) -> dict:
    entry, out = job
    start = time.time()
    try:
        res = _W["ex"].run(entry, Path(out))
        res["ok"] = True
    except Exception as exc:  # recorded, the run continues
        res = {
            "file": _W["tc"].rel(entry["file"]),
            "ok": False,
            "error": f"{type(exc).__name__}: {exc}",
            "trace": traceback.format_exc(limit=5),
        }
    res["wall_s"] = round(time.time() - start, 2)
    res["pid"] = os.getpid()
    return res


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--freecad", default=str(Path.home() / "src/FreeCAD"))
    ap.add_argument("--build", default=None, help="default: <freecad>/build/release")
    ap.add_argument("--out", required=True)
    ap.add_argument("--workers", type=int, default=6)
    ap.add_argument("--limit", type=int, default=0, help="only the first N TUs (testing)")
    ap.add_argument("--match", default="", help="only TUs whose path contains this text")
    ap.add_argument("--maxtasks", type=int, default=40, help="TUs per worker before restart")
    a = ap.parse_args(argv)

    tc = Toolchain(Path(a.freecad), Path(a.build or Path(a.freecad) / "build/release"))
    out = Path(a.out).expanduser()
    tus_dir = out / "tus"
    tus_dir.mkdir(parents=True, exist_ok=True)

    all_entries = load_compile_db(tc)
    entries = [e for e in all_entries if a.match in e["file"] and not tc.skip_tu(e["file"])]
    skipped = len(all_entries) - len([e for e in all_entries if not tc.skip_tu(e["file"])])
    # Largest sources first: better load balance at the end of the run.
    entries.sort(
        key=lambda e: os.path.getsize(e["file"]) if os.path.exists(e["file"]) else 0, reverse=True
    )
    if a.limit:
        entries = entries[: a.limit]
    jobs = [(e, str(tus_dir / _out_name(tc, e["file"]))) for e in entries]
    todo = [j for j in jobs if not Path(j[1]).exists()]

    libv, ccv = tc.check_versions()  # refuses to run on a libclang/compiler mismatch
    rev = subprocess.run(
        ["git", "-C", str(tc.freecad), "describe", "--tags", "--always"],
        capture_output=True,
        text=True,
    ).stdout.strip()
    run_rec = {
        "t": "run",
        "tool": "extract-cpp",
        "schema": SCHEMA_VERSION,
        "freecad_rev": rev,
        "compiler": tc.version(),
        "libclang": f"{tc.libclang} ({libv})",
        "started": datetime.now(UTC).isoformat(timespec="seconds"),
        "tus_total": len(jobs),
        "tus_todo": len(todo),
        "tus_skipped_not_freecad": skipped,
        "workers": a.workers,
    }
    with (out / "runs.jsonl").open("a") as fh:
        fh.write(dumps(run_rec) + "\n")

    log = (out / "progress.log").open("a", buffering=1)
    fails = (out / "failures.jsonl").open("a", buffering=1)
    log.write(
        f"# {run_rec['started']} start: {len(todo)} of {len(jobs)} TUs to do, "
        f"{a.workers} workers, FreeCAD {rev}\n"
    )
    t0, done, failed = time.time(), 0, 0
    ctx = mp.get_context("spawn")
    with ctx.Pool(
        a.workers,
        initializer=_init_worker,
        initargs=(str(tc.freecad), str(tc.build)),
        maxtasksperchild=a.maxtasks,
    ) as pool:
        for res in pool.imap_unordered(_work, todo, chunksize=1):
            done += 1
            if not res["ok"]:
                failed += 1
                fails.write(json.dumps(res) + "\n")
            el = time.time() - t0
            eta = el / done * (len(todo) - done)
            log.write(
                f"{datetime.now().strftime('%H:%M:%S')} {done}/{len(todo)} "
                f"{'ok ' if res['ok'] else 'ERR'} {res['wall_s']:6.1f}s "
                f"err={res.get('errors', '-')} rec={res.get('records', '-')} "
                f"eta={eta / 3600:.1f}h {res['file']}\n"
            )
    total = time.time() - t0
    log.write(f"# finished: {done} TUs, {failed} failed, {total / 3600:.2f} h\n")
    print(f"done: {done} TUs, {failed} failed, {total / 60:.1f} min -> {out}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
