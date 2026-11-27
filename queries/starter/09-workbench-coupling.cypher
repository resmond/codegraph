// 09 Workbench coupling: call edges between different modules (who depends on whom)
MATCH (a:Function)-[:CALLS]->(b:Function)
MATCH (a)-[:DECLARED_IN]->(fa:File), (b)-[:DECLARED_IN]->(fb:File)
WHERE fa.module <> fb.module AND NOT fa.external AND NOT fb.external
RETURN fa.module AS from, fb.module AS to, count(*) AS calls
ORDER BY calls DESC
LIMIT 40
