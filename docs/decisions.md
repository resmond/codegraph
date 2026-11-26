# Decisions

Source: planning chat and the plan doc
https://claude.ai/artifact/8WNm9gmPa3hgiYqSdeHymm (2026-11-26).
Each entry: the decision, then why.

## 1. Monorepo package layout and dependency rules
TODO: packages, and which may depend on which.

## 2. Regenerable parsed facts vs human annotations
TODO: where parsed facts live (rebuilt from source on each index run), where annotations
live, and how annotations stay attached when parsed facts are regenerated.

## 3. Tool versions (approved 2026-11-26)
- **Parser:** libclang 21 (system `libclang1-21` 21.1.8, `/usr/lib/llvm-21/lib/libclang-21.so.1`),
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
