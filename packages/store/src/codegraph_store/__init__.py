"""Load a codegraph fact run into Neo4j (decisions.md §1-2).

``model.build_graph`` reads a run directory and returns deduplicated nodes and relationships
(pure Python, no database); ``neo4j_load.load`` wipes the fact part of the database and writes
them. Annotation nodes (``:Annotation``) are never deleted. Entry point: ``cg-load``.
"""
