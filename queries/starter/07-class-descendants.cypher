// 07 Classes deriving from a class (up to 3 levels), counted per workbench
WITH 'App::DocumentObject' AS cls
MATCH (d:Class)-[:INHERITS*1..3]->(b:Class {qname: cls})
WITH DISTINCT d
MATCH (d)-[:DECLARED_IN]->(f:File)
RETURN f.module AS module, count(d) AS classes, collect(d.qname)[..8] AS examples
ORDER BY classes DESC
