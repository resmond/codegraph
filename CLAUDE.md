# codegraph

TODO: one-paragraph description of what codegraph is and what it indexes
(the FreeCAD source tree, via `compile_commands.json`, into Neo4j).

Design decisions and their reasons are in [docs/decisions.md](docs/decisions.md).
Read it before changing structure, dependencies or deployment.

## Machines
| Machine | Role | How |
|---|---|---|
| NUC (this machine) | Runs the agent session; holds this repo, the FreeCAD build tree, `compile_commands.json`, IntelliJ and the UI | Claude Code in VS Code or tmux, Remote Control on |
| AMD server (`ssh amd-speech`, 192.168.1.16) | No agent. Also hosts latency-sensitive speech services | Changed only via the deployment repo, applied over SSH from the NUC |

## Rules for Claude
1. Server changes go through the deployment repo, `~/configs/homelab` (its own CLAUDE.md
   rules apply there): edit, commit, then apply over SSH with its `scripts/`
   (`docker compose up`, checks, logs; compose dir `/opt/speech` on the server).
   Never edit files live on the server.
2. Never run two independent agents on one working tree; use
   `claude remote-control --spawn worktree` for parallel sessions.
3. The AMD server shares its GPU/CPU with speech services: check load before heavy jobs there.
4. Parsed facts are regenerable; human annotations are not. Never overwrite or delete
   annotations when re-indexing. TODO: name where each lives.
5. Commit with a clear message after each working change.

## Layout
TODO: monorepo package layout and dependency rules (see decisions.md).

## Tool versions
TODO: pinned versions (see decisions.md).
