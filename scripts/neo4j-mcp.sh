#!/usr/bin/env bash
# Start the official Neo4j MCP server (github.com/neo4j/mcp, GPL-3.0) for codegraph's Neo4j,
# READ-ONLY and with telemetry off. Used by .mcp.json (Claude Code, stdio transport).
# The password is read over SSH from the server's compose .env (as `cg-load` does), held only in
# this process's environment, never printed or written. Requires APOC on the server
# (homelab hosts/amd-speech/codegraph/compose.yml). Docs: docs/explore-and-refactor.md.
# Manual check:  scripts/neo4j-mcp.sh --check   (handshake + tool list, then exits)
set -euo pipefail
VERSION="2.1.2"
HOST="${CODEGRAPH_SSH_HOST:-amd-speech}"
ENV_FILE="${CODEGRAPH_ENV_FILE:-/opt/codegraph/.env}"

line=$(ssh -n -o BatchMode=yes -o ConnectTimeout=5 "$HOST" "grep -m1 '^NEO4J_AUTH=' $ENV_FILE") \
  || { echo "neo4j-mcp.sh: cannot read NEO4J_AUTH from $HOST:$ENV_FILE" >&2; exit 1; }
auth=${line#NEO4J_AUTH=}
export NEO4J_MCP_URI="${NEO4J_MCP_URI:-bolt://192.168.1.16:7687}"
export NEO4J_MCP_USERNAME="${auth%%/*}"
export NEO4J_MCP_PASSWORD="${auth#*/}"
export NEO4J_MCP_DATABASE="neo4j"
export NEO4J_MCP_READ_ONLY="true"       # no write-cypher tool at all
export NEO4J_MCP_TELEMETRY="false"
export NEO4J_MCP_REQUEST_TIMEOUT="2m"
export NEO4J_MCP_LOG_LEVEL="warning"
unset line auth

run() { exec uvx --quiet --from "neo4j-mcp-server==$VERSION" neo4j-mcp-server "$@"; }
if [[ "${1:-}" == --check ]]; then
  { printf '%s\n' \
    '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{"protocolVersion":"2025-06-18","capabilities":{},"clientInfo":{"name":"check","version":"0"}}}' \
    '{"jsonrpc":"2.0","method":"notifications/initialized"}' \
    '{"jsonrpc":"2.0","id":2,"method":"tools/list"}'; sleep 15; } \
    | timeout 60 uvx --quiet --from "neo4j-mcp-server==$VERSION" neo4j-mcp-server 2>&1 | head -c 4000
  echo; exit 0
fi
run "$@"
