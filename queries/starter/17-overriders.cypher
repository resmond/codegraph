// 17 Methods that override a virtual method (directly or further down), per workbench
WITH 'App::DocumentObject::execute' AS qname
MATCH (o:Function)-[:OVERRIDES*1..6]->(m:Function {qname: qname})
WITH DISTINCT o
MATCH (o)-[:DECLARED_IN]->(f:File)
RETURN f.module AS module, count(o) AS overriders, collect(o.qname)[..6] AS examples
ORDER BY overriders DESC
