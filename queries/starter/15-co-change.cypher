// 15 Files that change together with a file in git history (hidden coupling)
WITH 'src/App/Document.cpp' AS path
MATCH (f:File {path: path})-[r:CO_CHANGED]-(o:File)
RETURN o.path AS file, o.module AS module, r.n AS commits_together
ORDER BY commits_together DESC
LIMIT 40
