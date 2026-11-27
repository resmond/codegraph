// 10 Hotspots: complex functions in frequently changed files (complexity x git commits)
MATCH (f:Function)-[:DECLARED_IN]->(file:File)
WHERE f.def AND f.cc >= 20 AND file.commits IS NOT NULL AND NOT file.generated
RETURN f.qname AS function, f.cc AS cc, f.lines AS lines, file.path AS file, file.commits AS commits,
       f.cc * file.commits AS score
ORDER BY score DESC
LIMIT 40
