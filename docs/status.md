# Status — 2026-11-26

## Done
- Neo4j `neo4j:5.26.34-community` running on amd-speech (`/opt/codegraph`), heap 8g, page cache 16g,
  6 CPUs, 28g; Bolt `bolt://192.168.1.16:7687`, browser `:7474`; firewalled to the NUC only.
  Deployed from `~/configs/homelab` (`scripts/deploy-codegraph.sh`). Password: server `.env` only.
- Decisions §3–§6 approved (`docs/decisions.md`): libclang 21, uv Python, Neo4j sizing, machine roles.
- UI moved out of codegraph: the graph UI is qt-graphkit (github.com/resmond/qt-graphkit), so
  codegraph is backend only (schema, indexer, annotation store).

## Open decisions
- §1 package layout: option B recommended (uv workspace, one package per stage), minus `apps/ui`.
- §2 facts vs annotations: option B recommended (annotations as files in git, overlay in Neo4j).

## Parser facts (probe 2026-11-26)
- Library: Ubuntu `libclang-21.so.1` (21.1.8 = the compiler's version), Python bindings
  `clang==21.1.7`, headers from the pixi resource dir `~/src/FreeCAD/.pixi/envs/default/lib/clang/21`.
  Correction: the pixi `libclang.so.13` is clang 23.1.4, not 21; it caused the
  `__builtin_ia32_*` errors and truncated TUs at clang's 20-error limit (now `-ferror-limit=0`).
- libclang ignores the conda compiler's `.cfg` include setup: pass `-nostdinc -nostdinc++`, then
  `-isystem` for each path `clang++ -E -x c++ - -v` lists (pixi include, conda GCC 13 libstdc++,
  clang builtins, conda sysroot). Without this, Boost headers are not found.
- Input: `~/src/FreeCAD/build/release/compile_commands.json`, 3,692 TUs, 22 workbenches, FreeCAD at
  weekly-2026.11.26 (`226841e6cd`).
- Probe: Document.cpp 12.8 s / 0 errors, TopoShape.cpp 9.9 s / 0, ViewProviderSketch.cpp 19.5 s /
  4 errors (`__builtin_ia32_sqrtss`, x86 intrinsics); peak 1.2 GB per process.

## Overnight extraction (built 2026-11-26)
- Workspace per decision §1 option B: `packages/schema`, `extract-cpp`, `extract-py`, `extract-git`.
- C++: 3,692 compile entries; 1,525 skipped as not FreeCAD code (src/3rdParty, qrc_*, moc_*),
  about 2,167 parsed. Test on the 24 largest: 7-51 s each, 1.7 min on 6 workers, 0 failures.
  First full run (18:54) used the clang-23 library by mistake: 25% of TUs had SIMD errors and 8+
  were truncated. Stopped at 1,638/2,167 and kept as `<run>-clang23-partial`; restarted 19:47
  with libclang 21.1.8: 0 errors in the first 52 TUs (Area.cpp: 15,649 records vs 2,665).
- Output: `~/.cache/codegraph/runs/<date>-freecad-<rev>/` with `tus/*.jsonl` (one per TU),
  `python.jsonl`, `git.jsonl`, `progress.log`, `failures.jsonl`, `runs.jsonl`.
- Launch: `scripts/overnight-parse.sh` (systemd user unit `codegraph-parse`, blocks sleep).
- Known gaps: no `overrides` edges yet (bindings lack overridden-cursor access); per-worker
  header dedup means some header facts repeat — the loader dedupes by (usr, file, line, def).

## Morning list (2026-11-27)
- [x] Check the overnight run finished: `tail -3 <run>/progress.log`, `failures.jsonl` empty,
      errors per TU (expect 0). Delete `<run>-clang23-partial` when no longer needed.
- [x] `packages/store`: Neo4j loader for the run — constraints/indexes, dedupe symbols by
      (usr, file, line, def), stub nodes for external call/type targets, load python.jsonl and
      git.jsonl, link files to churn and modules.
- [ ] Test code: the 193 TUs under `tests/` were parsed but mostly skipped, because
      `is_project_file` only counts `src/` and `build/`. Count `tests/` as project code (flagged
      as test), re-parse just those (`--match /tests/`, ~10 min), and load "test calls code"
      edges.

## Overnight run result and first load (2026-11-26, 21:55-22:30)
- Run `2026-11-26-freecad-226841e6cd`: 2,167 TUs in 1.04 h, 0 failed; 1 TU with a diagnostic
  (`src/Base/PyTools.c`: "argument unused: -nostdinc++", harmless; C TUs should drop that flag).
  3.23 M records, 794 MB. The clang-23 partial and test runs are to be deleted.
- `uv run cg-load --run <run>` (`--dry-run` first): builds the graph in 30 s / 1.1 GB, loads in
  48 s. Loaded: 113,491 symbols (+43,675 external stubs), 14,525 files, 141 modules,
  28,443 Python nodes; 394,496 CALLS, 222,869 USES_TYPE, 4,543 INHERITS, 32,160 INCLUDES,
  28,569 CO_CHANGED, 10,635 IMPORTS. Database counts match the model.
- Sanity: 311 classes derive from App::DocumentObject; Sketcher->Part is the largest
  cross-workbench call flow (1,330 edges).
- Known gaps: File nodes include git-only paths (deleted files, docs) - no `exists` flag yet;
  Python `bases` are a property, not INHERITS edges; no `overrides` edges; `test` is a path
  heuristic (`tests/`, `/Test`). Test TUs are still the next item below.
