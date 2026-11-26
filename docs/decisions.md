# Decisions

Source: planning chat and the plan doc
https://claude.ai/artifact/8WNm9gmPa3hgiYqSdeHymm (2026-11-26).
Each entry: the decision, then why.

## 1. Monorepo package layout and dependency rules
TODO: packages, and which may depend on which.

## 2. Regenerable parsed facts vs human annotations
TODO: where parsed facts live (rebuilt from source on each index run), where annotations
live, and how annotations stay attached when parsed facts are regenerated.

## 3. Tool versions
TODO: Neo4j, language runtime(s), parser/clang version, other pinned tools.

## 4. Which machine runs what
- **NUC:** the single agent session, the codegraph repo, FreeCAD build tree,
  `compile_commands.json`, IntelliJ, the UI. Why: everything the agent works on is here.
- **AMD server:** no agent for now; changes only via the deployment repo over SSH.
  Why: it hosts latency-sensitive speech services; versioned changes prevent drift.
- **Later:** a server-side session (`claude --rc` in tmux) once indexing moves to the
  server or a long debugging session is needed.
- TODO: where Neo4j and the indexer run.

## 5. Neo4j memory and CPU settings
TODO: heap, page cache, CPU limits, and on which host.

## 6. Server changes go through the deployment repo
The deployment repo is `~/configs/homelab`. Edit it, commit, then apply over SSH from the
NUC. Why: every server change stays versioned and reviewable, and the server never
drifts from the repo.
