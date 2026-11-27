// 05 Call neighbourhood as a graph: callers -> function -> FreeCAD callees
WITH 'App::Document::recompute' AS qname
MATCH (f:Function {qname: qname})
OPTIONAL MATCH p1 = (:Function)-[:CALLS]->(f)
OPTIONAL MATCH p2 = (f)-[:CALLS]->(c:Function) WHERE NOT c:External
RETURN f, collect(DISTINCT p1)[..40] AS callers, collect(DISTINCT p2)[..40] AS callees
