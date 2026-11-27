# Decisions

Source: planning chat and the plan doc
https://claude.ai/artifact/8WNm9gmPa3hgiYqSdeHymm (2026-11-26).
Each entry: the decision, then why.

## 1. Monorepo package layout and dependency rules (decided 2026-11-26: option B)
uv workspace, one package per stage, backend only (the UI is qt-graphkit,
github.com/resmond/qt-graphkit):
```
packages/
  schema/        record types and schema version                      deps: none
  extract-cpp/   libclang 21 -> fact records (JSONL per TU)           deps: schema
  extract-py/    Python ast -> fact records                           deps: schema
  extract-git/   git history -> churn, authors, co-change records     deps: schema
  store/         load records into Neo4j, query helpers  (next)       deps: schema
  annotations/   annotation files, re-attach, orphan report (later)   deps: schema, store
  cli/           `codegraph ...` entry points (later)                 deps: all
```
Rules: extractors never import `store`; they write files and the loader reads them, so the slow
parse and the frequent load run independently. `schema` imports nothing. Why: parsing 3,692 TUs
takes hours; loading is iterated often. (Options A and C, and the TypeScript UI, are dropped.)

## 2. Regenerable parsed facts vs human annotations (decided 2026-11-26: option B)
Facts: JSONL runs under `~/.cache/codegraph/runs/<date>-freecad-<rev>/`, loaded into Neo4j; both
can be wiped and rebuilt. Annotations: files in this repo's `annotations/`, keyed by stable
symbol ID, loaded into Neo4j as an overlay after each fact load. Neo4j needs no backups.
The options considered are kept below for the record.

Common to all options:
- **Facts are disposable.** Each index run writes fact records (gitignored cache, e.g.
  `~/.cache/codegraph/<run>/`) and reloads them; the graph's fact part can be wiped and
  rebuilt at any time. Start with full rebuilds; incremental per-file loads later if needed.
- **Annotations attach by a stable key, never by Neo4j node id or file:line.** C++: the
  libclang USR (stable across rebuilds while the signature stays); Python: the qualified name.
  Each annotation also stores the last-seen file, line and a snippet hash, so one whose key
  vanished (renamed or removed symbol) is reported as an orphan with a re-anchor hint,
  never silently dropped.
- Neo4j Community has a single user database, so "a second database for annotations" is
  not available: separation is by label or by a separate store.

**Option A — both in Neo4j, separated by label.**
Facts: `(:Symbol {usr, …})` etc., tagged with the run id. Annotations: `(:Annotation {key, …})`
linked by `MATCH … WHERE s.usr = a.key` after each load. Re-index = delete fact labels only.
+ One place to query; UI edits are a single write.
− Annotations live only in the DB: a careless wipe or a broken migration loses them, so they
  need their own backups; edits aren't reviewable as diffs.

**Option B — annotations as files in git, loaded into Neo4j as an overlay (recommended).**
`annotations/` in this repo (YAML or Markdown with front matter), one entry per key.
After every fact load, the loader creates the `(:Annotation)` overlay from the files.
The UI writes annotation files through the API; commits are made like any other change.
+ Survives any DB wipe; versioned and reviewable, like the homelab repo; Neo4j holds
  nothing that can't be rebuilt, so it needs no backups.
− UI edits become file writes plus commits; two people editing one entry can conflict.

**Option C — separate annotation store (SQLite on the NUC).**
Facts in Neo4j; annotations in SQLite keyed by symbol key, joined in the API layer.
+ Clean separation; quick UI writes.
− Graph queries can't see annotations without a sync step; a second store to back up.

Chosen: B. It keeps Neo4j fully regenerable, which matches deploying it as a
disposable container on amd-speech, and puts the only irreplaceable data under git.

## 3. Tool versions (approved 2026-11-26)
- **Parser (revised after the probe, see status.md):** FreeCAD's pixi libclang 21.1.8
  (`~/src/FreeCAD/.pixi/envs/default/lib/libclang.so.13`) with its own resource dir; the system
  `libclang1-21` lacks clang's builtin headers. Originally: libclang 21 (system `libclang1-21` 21.1.8,
  Python bindings `clang==21.1.*`. Index from `~/src/FreeCAD/build/release/compile_commands.json`.
  Why: matches the clang++ 21.1.8 that produced the compile database, so flags parse as built.
- **Runtime:** codegraph's own uv-managed Python (3.13 or 3.14), not FreeCAD's pixi env.
  Why: keeps codegraph independent of FreeCAD's environment updates.
- **Neo4j:** `neo4j:5.26.34-community` (5.26 LTS; newest patch on Docker Hub 2026-11-24).
  Why: LTS line; exact tag so upgrades are deliberate commits.

## 4. Which machine runs what
- **NUC:** the single agent session, the codegraph repo, FreeCAD build tree,
  `compile_commands.json`, IntelliJ, the UI. Why: everything the agent works on is here.
- **AMD server:** no agent for now; changes only via the deployment repo over SSH.
  Why: it hosts latency-sensitive speech services; versioned changes prevent drift.
- **Later:** a server-side session (`claude --rc` in tmux) once indexing moves to the
  server or a long debugging session is needed.
- **Neo4j:** Docker on `amd-speech`, deployed via `~/configs/homelab`. Why: the server has
  ~117 GiB free RAM; the NUC has no Docker and ~16 GiB available.
- **Indexer:** on the NUC, next to the source and build tree, writing to Neo4j over the LAN.

## 5. Neo4j memory and CPU settings (approved 2026-11-26)
- Heap 8 GB (initial = max), page cache 16 GB.
- Container limits `cpus: 6`, `mem_limit: 28g`.
- Why: leaves 10 threads and ~90 GB for speech services and the rest. Starting point:
  revisit after the first full index, from the store size.

## 6. Server changes go through the deployment repo
The deployment repo is `~/configs/homelab`. Edit it, commit, then apply over SSH from the
NUC. Why: every server change stays versioned and reviewable, and the server never
drifts from the repo.

---

## Facts gathered (2026-11-26) — input for 3–5

### FreeCAD source (NUC)
- Tree `~/src/FreeCAD` at `226841e6cd` (weekly-2026.11.26), built with pixi 0.85.0.
- Two builds, `build/release` and `build/debug`; each `compile_commands.json` has
  3,692 entries (~9.6 MB). Compiler: pixi env `clang++` 21.1.8 (conda-forge).
- Tracked sources: 4,681 C++ (`.cpp/.cxx/.h/.hpp`), 1,946 Python. `src/` 479 MB, `build/` 5.3 GB.

### Tools on the NUC
| Tool | System | FreeCAD pixi env |
|---|---|---|
| clang / libclang | `libclang1-21` 21.1.8 (`/usr/lib/llvm-21/lib/libclang-21.so.1`); no `clang`, `clangd` binaries | `clang++` 21.1.8; no `clangd`, `clang-tidy` |
| Python | 3.14.4, uv 0.13.7 | 3.13.18 (no `clang` bindings) |
| CMake / Ninja | not installed | 4.4.3 / 1.13.2 |
| gcc | 15.2.0 | — |
| git | 2.53.0 | — |
| Docker, Java, Node | not installed | — |

### Hosts
| | NUC | AMD server (`amd-speech`) |
|---|---|---|
| CPU | 16 threads | Ryzen 7 5800X, 16 threads, load ~0.0 |
| RAM | 30 GiB, ~16 GiB available (desktop, FreeCAD, IntelliJ) | 125 GiB, ~117 GiB available |
| Disk | 1.6 TB free on /home | 68 GB free on / (60% used) |
| Docker | none | 29.1.3, Compose 2.40.3; no Neo4j yet |
| Other load | interactive desktop | speech (whisper GPU, piper), Ollama, HA, ESPHome, Open WebUI; GPU 2.7/8 GB |

### Proposal (approved 2026-11-26 with Neo4j 5.26 LTS; now in 3–5 above)
- **Parser:** libclang 21 to match the compiler that produced `compile_commands.json`;
  Python bindings pinned to the same major (`clang==21.1.*` from PyPI), loaded against
  `/usr/lib/llvm-21/lib/libclang-21.so.1`. Use the `release` build's database.
- **Runtime:** codegraph's own uv-managed Python (3.13 or 3.14), not FreeCAD's pixi env.
- **Neo4j:** run on `amd-speech` in Docker, deployed via `~/configs/homelab`: that's where
  the RAM is, and the NUC has neither Docker nor spare memory. Pin one exact image tag
  (latest 5.26 LTS or current 2025.x; choose and pin).
- **Neo4j sizing (starting point):** heap 8 GB initial = max, page cache 16 GB,
  container limits `cpus: 6`, `mem_limit: 28g`. That leaves 10 threads and ~90 GB for
  speech and the rest. Revisit after the first full index, from the store size.
- **Indexer:** on the NUC (next to the source and build tree), writing to Neo4j over the LAN.
