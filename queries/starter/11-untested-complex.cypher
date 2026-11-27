// 11 Complex functions with no direct caller from the C++ test suite (direct calls only)
MATCH (f:Function)
WHERE f.def AND f.cc >= 40 AND f.test IS NULL AND f.file STARTS WITH 'src/'
  AND NOT EXISTS { MATCH (:Function {test: true})-[:CALLS]->(f) }
RETURN f.qname AS function, f.cc AS cc, f.lines AS lines, f.file AS file
ORDER BY cc DESC
LIMIT 50
