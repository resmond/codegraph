// 14 Most-included FreeCAD headers (changing these rebuilds the most)
MATCH (h:File)<-[:INCLUDES]-(s:File)
WHERE NOT h.external AND h.path ENDS WITH '.h'
RETURN h.path AS header, h.module AS module, count(s) AS included_by
ORDER BY included_by DESC
LIMIT 40
