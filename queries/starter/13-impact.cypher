// 13 Impact of changing a function: transitive callers (up to 3 hops), counted per module
WITH 'Part::TopoShape::makeElementFillet' AS qname
MATCH (f:Function {qname: qname})<-[:CALLS*1..3]-(c:Function)
WITH DISTINCT c
MATCH (c)-[:DECLARED_IN]->(file:File)
RETURN file.module AS module, count(c) AS callers, sum(CASE WHEN c.test THEN 1 ELSE 0 END) AS tests,
       collect(c.qname)[..5] AS examples
ORDER BY callers DESC
