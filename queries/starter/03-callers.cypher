// 03 Who calls this function (direct callers, with call counts)
WITH 'App::Document::recompute' AS qname
MATCH (c:Function)-[r:CALLS]->(f:Function {qname: qname})
RETURN c.qname AS caller, c.file AS file, c.line AS line, r.n AS calls, coalesce(c.test, false) AS test
ORDER BY calls DESC, caller
LIMIT 100
