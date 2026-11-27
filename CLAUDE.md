# codegraph

codegraph turns the FreeCAD source tree into a queryable graph in Neo4j. Extractors parse
FreeCAD's C++ with libclang (via the build's `compile_commands.json`), its Python with `ast`,
and its git history, writing regenerable JSONL fact records; a loader puts them into Neo4j on
amd-speech, and human annotations (kept as files in git) are overlaid on top. The graph UI is
a separate project, qt-graphkit (github.com/resmond/qt-graphkit). Status: `docs/status.md`.

Design decisions and their reasons are in [docs/decisions.md](docs/decisions.md).
Read it before changing structure, dependencies or deployment.

## Machines
| Machine | Role | How |
|---|---|---|
| NUC (this machine) | Runs the agent session; holds this repo, the FreeCAD build tree, `compile_commands.json`, IntelliJ and the UI | Claude Code in VS Code or tmux, Remote Control on |
| AMD server (`ssh amd-speech`, 192.168.1.16) | No agent. Runs Neo4j (Docker); also hosts latency-sensitive speech services | Changed only via the deployment repo, applied over SSH from the NUC |

## Rules for Claude
1. Server changes go through the deployment repo, `~/configs/homelab` (its own CLAUDE.md
   rules apply there): edit, commit, then apply over SSH with its `scripts/`
   (`docker compose up`, checks, logs; compose dir `/opt/speech` on the server).
   Never edit files live on the server.
2. Never run two independent agents on one working tree; use
   `claude remote-control --spawn worktree` for parallel sessions.
3. The AMD server shares its GPU/CPU with speech services: check load before heavy jobs there.
4. Parsed facts are regenerable; human annotations are not. Never overwrite or delete
   annotations when re-indexing. Facts: `~/.cache/codegraph/runs/<run>/` (never committed).
   Annotations: `annotations/` in this repo, keyed by USR / Python qualified name (§2).
5. Commit with a clear message after each working change.

## Layout (uv workspace, decisions.md §1)
| Package | Does | Deps |
|---|---|---|
| `packages/schema` | record types, `JsonlWriter`, schema version | none |
| `packages/extract-cpp` | `cg-extract-cpp`: libclang -> `tus/*.jsonl`, parallel + resumable | schema |
| `packages/extract-py` | `cg-extract-py`: Python ast -> `python.jsonl` | schema |
| `packages/extract-git` | `cg-extract-git`: churn, authors, co-change -> `git.jsonl` | schema |
| `packages/store` (next) | load runs into Neo4j | schema |
Extractors never import `store`. Long C++ runs: `scripts/overnight-parse.sh`.

## Tool versions
- libclang 21.1.8 from FreeCAD's pixi env (`.pixi/envs/default/lib/libclang.so.13`), Python
  bindings `clang==21.1.7`; include setup in `extract-cpp/toolchain.py`
- Python via uv (own env, not FreeCAD's pixi env)
- Neo4j `neo4j:5.26.34-community` on `amd-speech` (heap 8G, page cache 16G, 6 CPUs, 28g)
- Index input: `~/src/FreeCAD/build/release/compile_commands.json`

Details and reasons: decisions.md §3–5.
