// 18 Every call site of a function (file:line:col) - the edit list for a signature change
WITH 'App::Document::recompute' AS qname
MATCH (c:Function)-[r:CALLS]->(f:Function {qname: qname})
UNWIND r.sites AS site
WITH c, site, split(site, ':') AS p
RETURN p[0] AS file, toInteger(p[1]) AS line, toInteger(p[2]) AS col, c.qname AS in_function
ORDER BY file, line, col
