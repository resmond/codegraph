// 08 Members of a class: methods, fields, nested types (with complexity for methods)
WITH 'App::Document' AS cls
MATCH (c:Class {qname: cls})-[:CONTAINS]->(m:Symbol)
RETURN m.kind AS kind, m.name AS name, m.access AS access, m.flags AS flags, m.cc AS cc, m.lines AS lines, m.sig AS signature
ORDER BY kind, name
