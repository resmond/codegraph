// 20 Override chain of a method up to the base declaration, as a graph
WITH 'PartDesign::Pad::execute' AS qname
MATCH p = (m:Function {qname: qname})-[:OVERRIDES*1..6]->(:Symbol)
RETURN p
