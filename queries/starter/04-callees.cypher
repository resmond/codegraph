// 04 What this function calls (FreeCAD functions and external libraries)
WITH 'App::Document::recompute' AS qname
MATCH (f:Function {qname: qname})-[r:CALLS]->(c:Symbol)
RETURN c.qname AS callee, coalesce(c.name, '') AS name, c:External AS external, c.file AS file, r.n AS calls
ORDER BY external, calls DESC
LIMIT 200
