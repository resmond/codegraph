// 06 Class ancestors (base classes, up to 6 levels) as a graph
WITH 'PartDesign::Pad' AS cls
MATCH p = (c:Class {qname: cls})-[:INHERITS*1..6]->(:Symbol)
WHERE c.def
RETURN p
