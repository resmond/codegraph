# Cypher queries

`starter/`: 16 read-only queries for getting to know the graph (schema, callers/callees, class
hierarchy, members, workbench coupling, hotspots, untested complex code, tests for a function,
change impact, include fan-in, git co-change, Python importers).

Each file starts with a `// title` comment; queries that need an input take it from the first
`WITH '...' AS name` line, so edit that value and run.

## Use in the Neo4j Browser
Open http://192.168.1.16:7474, then the star icon (Favorites) in the left bar, and drag all
`starter/*.cypher` files onto it (or use its import button). Each becomes a saved query named by
its first comment line. Graph-shaped results (01, 05, 06) show as graphs; the rest as tables.

## Keep them working
`uv run cg-check-queries` runs every query read-only and fails if one errors or returns no rows
(e.g. an example symbol renamed after a FreeCAD update).
