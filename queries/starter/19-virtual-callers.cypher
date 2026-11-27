// 19 Callers of a method including calls through the base classes it overrides (virtual dispatch)
WITH 'PartDesign::Pad::execute' AS qname
MATCH (m:Function {qname: qname})-[:OVERRIDES*0..6]->(target:Function)
MATCH (c:Function)-[r:CALLS]->(target)
RETURN target.qname AS called_as, c.qname AS caller, c.file AS file, r.n AS calls
ORDER BY called_as, calls DESC
LIMIT 100
