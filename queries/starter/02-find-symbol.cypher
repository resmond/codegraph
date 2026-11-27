// 02 Find a symbol by (part of) its name - edit the text on the first line
WITH 'recompute' AS text
MATCH (s:Symbol)
WHERE s.name = text OR s.qname ENDS WITH '::' + text
RETURN s.kind AS kind, s.qname AS qname, s.file AS file, s.line AS line, s.def AS definition
ORDER BY qname
LIMIT 50
