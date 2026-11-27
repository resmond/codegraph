// 12 Tests that call a function directly
WITH 'Base::Vector2d::Vector2d' AS qname
MATCH (t:Function {test: true})-[:CALLS]->(f:Function)
WHERE f.qname = qname OR f.qname STARTS WITH qname
RETURN t.qname AS test, t.file AS file, f.qname AS calls
ORDER BY file, test
LIMIT 100
