// 16 Python modules that import a module (FreeCAD's own or external)
WITH 'Part' AS module
MATCH (m:PyModule)-[r:IMPORTS]->(t)
WHERE t.id = module OR t.id ENDS WITH '.' + module
RETURN m.id AS importer, m.file AS file, t.id AS imports, r.how AS resolved, r.names AS names
ORDER BY importer
LIMIT 100
