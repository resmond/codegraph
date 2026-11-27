# Exploring the graph and using it for supervised refactoring

Status and plan, 2026-11-27. The graph model itself is documented in
`packages/store/src/codegraph_store/model.py`; current counts are in `docs/status.md`.

Goal: use the graph to plan, apply, check and record small, reviewed refactoring and enhancement
edits to FreeCAD, one at a time, with the human deciding at each step.

## 1. Schema 0.2 at a glance

- Nodes: `Module` (workbench/area), `File` (with git churn), `Symbol` + kind label
  (`Function`, `Class`, `Field`, `Variable`, `Type`, `Enum`, `Namespace`; key: libclang USR),
  `Symbol:External` (Qt, OpenCASCADE, std, Boost targets), `PyModule`/`PyClass`/`PyFunc`,
  `PyExternal`, `Run`.
- Relationships: `CALLS {n, sites}`, `OVERRIDES`, `USES_TYPE`, `INHERITS {access}`, `CONTAINS`, `DECLARED_IN`,
  `INCLUDES`, `CO_CHANGED {n}`, `IMPORTS {how, names}`.
- Test code: `File.test`, `Symbol.test` (C++ under `tests/`).
- Draw it: `CALL db.schema.visualization()` in the Browser (query 01).

## 2. Tools for exploring

| Tool | Use | Status |
|---|---|---|
| Neo4j Browser, http://192.168.1.16:7474 | Ad-hoc Cypher, expanding nodes; starter queries in `queries/starter/` | In use |
| Official Neo4j MCP server (github.com/neo4j/mcp, GPL-3.0), read-only | Claude queries the graph during sessions (impact, callers, hierarchy) | Working: `.mcp.json` + `scripts/neo4j-mcp.sh` (APOC deployed 2026-11-27) |
| Sourcetrail community fork (github.com/petermost/Sourcetrail, GPL-3.0) | Interactive C++ navigation of FreeCAD from `compile_commands.json`, next to the source | To try |
| NeoDash Labs (Apache-2.0, best-effort maintenance) | Saved dashboards: hotspots, coupling, test reach | To try |
| Bloom / Explore | Point-and-click exploration | Skipped: not free on Community Edition locally |
| qt-graphkit (github.com/resmond/qt-graphkit) | The long-term custom UI | Phase 1b |

## 3. Open-source assets to borrow from

- Code-graph vocabularies: **Kythe** (node/edge kinds), **SCIP** (Sourcegraph symbol format).
  Align our names with one of them before the schema grows.
- Deeper graphs: **Joern** code property graph and **Fraunhofer AISEC `cpg`** (control and data
  flow); Joern has an LLM MCP server (codebadger, 2026). Reference only for now.
- Edit tools: **Serena** (MCP, symbol-level edits through clangd), **clang-tidy** fix-its and
  custom checks, **clangd** rename, **clang-include-cleaner / IWYU**, **ast-grep** (C++ and
  Python structural rewrites), **LibCST** (Python codemods). Status not re-checked (2026-11-27)
  except Serena.

## 4. The supervised edit loop (target)

1. Plan: query the impact set of the intended change (callers, overrides, includes, tests).
2. Record the intent as an annotation (decision §2), keyed by USR / qualified name.
3. Apply with a structural tool (clang-tidy / clangd / ast-grep / LibCST), never by text editing.
4. Build and run the affected tests.
5. Re-parse only the affected TUs; diff the graph before vs after against the stated intent.
6. Human review of the diff + graph delta; record the outcome on the annotation; commit.

## 5. To-do

Exploring (now):
- [x] Starter query pack, `queries/starter/` (16 queries; Browser favourites); checked by
      `uv run cg-check-queries` (2026-11-27: 16/16 return rows)
- [x] Official Neo4j MCP server v2.1.2, read-only, telemetry off: `scripts/neo4j-mcp.sh`,
      `.mcp.json` (project server `codegraph-neo4j`)
- [x] Enable APOC Core on the server (homelab d215072, deployed 2026-11-27): `--check` gives
      `neo4j-mcp 2.1.2`, tools `get-schema`, `read-cypher` (no write tool). A logged
      `gds.version` error is the optional GDS probe: harmless.
- [ ] Approve the `codegraph-neo4j` MCP server in a Claude Code session started in ~/codegraph
- [ ] Try the Sourcetrail fork on FreeCAD's `compile_commands.json`
- [ ] Try NeoDash Labs with a hotspot / coupling / test-reach dashboard (read-only DB user;
      Community Edition has no roles, so keep it on the NUC only)

Schema for editing (next, in order of value):
- [x] Call sites with positions: `CALLS.sites` ("file:line:col", max 200 per edge); schema 0.2,
      run 2026-11-27: 434,072 edges, 718,468 sites (queries 18, 19)
- [x] `OVERRIDES` edges via libclang's clang_getOverriddenCursors (ctypes): 24,816 (16,281 to
      FreeCAD methods, 8,535 to Qt/OCC/std); queries 17, 19, 20
- [ ] Python-to-C++ binding links: `*Py.xml` -> generated `*PyImp.cpp` wrappers -> C++ methods
- [ ] Macro usage (PROPERTY_HEADER, TYPESYSTEM_*, ...): expansion sites as edges
- [ ] Keep runs side by side instead of wiping (run id on facts), and a graph diff between runs
- [ ] Incremental re-parse of the TUs affected by an edit (from compile_commands + INCLUDES)
- [ ] Align node/edge names with Kythe or SCIP (decide which)
- [ ] `packages/annotations`: annotation files, overlay load, orphan report (decision §2), used
      as the record of refactor intents and review outcomes
- [ ] Transitive test reach (test -> function within N hops), and link FreeCAD's Python tests

Editing (after the schema items above):
- [ ] Pick the edit toolchain per kind of change (Serena vs clang-tidy vs ast-grep vs LibCST)
- [ ] First supervised refactor end to end, small and low risk (e.g. an include cleanup in one
      module, checked by include fan-in and a rebuild)
