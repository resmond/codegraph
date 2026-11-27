"""Write a ``model.Graph`` into Neo4j: wipe facts, create constraints, bulk-create in batches.

Everything except ``:Annotation`` nodes is fact data and is deleted first (decision §2: facts
are regenerable). Constraints come before the data so relationship MATCHes use the indexes.
"""

from __future__ import annotations

import time
from collections import defaultdict
from collections.abc import Callable, Iterable
from datetime import UTC, datetime

from neo4j import Driver

from .model import Graph

CONSTRAINTS = [
    ("Symbol", "usr"),
    ("File", "path"),
    ("Module", "name"),
    ("PyModule", "id"),
    ("PyClass", "id"),
    ("PyFunc", "id"),
    ("PyExternal", "id"),
    ("Run", "id"),
]
INDEXES = [
    ("Symbol", "name"),
    ("Symbol", "qname"),
    ("Symbol", "kind"),
    ("File", "module"),
    ("PyFunc", "name"),
    ("PyClass", "name"),
]

# rel key in Graph.rels -> (Cypher type, source match, target match)
REL_SPECS = {
    "MODULE_CONTAINS": ("CONTAINS", "(a:Module {name: r.a})", "(b:File {path: r.b})"),
    "DECLARED_IN": ("DECLARED_IN", "(a:Symbol {usr: r.a})", "(b:File {path: r.b})"),
    "CONTAINS_SYM": ("CONTAINS", "(a:Symbol {usr: r.a})", "(b:Symbol {usr: r.b})"),
    "CALLS": ("CALLS", "(a:Symbol {usr: r.a})", "(b:Symbol {usr: r.b})"),
    "USES_TYPE": ("USES_TYPE", "(a:Symbol {usr: r.a})", "(b:Symbol {usr: r.b})"),
    "INHERITS": ("INHERITS", "(a:Symbol {usr: r.a})", "(b:Symbol {usr: r.b})"),
    "OVERRIDES": ("OVERRIDES", "(a:Symbol {usr: r.a})", "(b:Symbol {usr: r.b})"),
    "INCLUDES": ("INCLUDES", "(a:File {path: r.a})", "(b:File {path: r.b})"),
    "CO_CHANGED": ("CO_CHANGED", "(a:File {path: r.a})", "(b:File {path: r.b})"),
    "PY_DECLARED_IN": ("DECLARED_IN", "(a:PyModule {id: r.a})", "(b:File {path: r.b})"),
    # {la}/{lb}: the endpoint labels the model put on each row (Python ids span labels)
    "PY_CONTAINS": ("CONTAINS", "(a:{la} {{id: r.a}})", "(b:{lb} {{id: r.b}})"),
    "IMPORTS": ("IMPORTS", "(a:{la} {{id: r.a}})", "(b:{lb} {{id: r.b}})"),
}
REL_PROPS = {
    "CALLS": ["n", "sites"],
    "INHERITS": ["access"],
    "CO_CHANGED": ["n"],
    "IMPORTS": ["how", "names"],
}

Log = Callable[[str], None]


def _batches(rows: list, size: int) -> Iterable[list]:
    for i in range(0, len(rows), size):
        yield rows[i : i + size]


def _write(driver: Driver, db: str, query: str, rows: list, size: int) -> int:
    n = 0
    for chunk in _batches(rows, size):
        driver.execute_query(query, rows=chunk, database_=db)
        n += len(chunk)
    return n


def wipe_facts(driver: Driver, db: str, log: Log) -> None:
    t = time.time()
    with driver.session(database=db) as s:
        s.run(
            "MATCH (n) WHERE NOT n:Annotation "
            "CALL (n) { DETACH DELETE n } IN TRANSACTIONS OF 10000 ROWS"
        ).consume()
    log(f"wiped fact nodes ({time.time() - t:.0f} s)")


def ensure_schema(driver: Driver, db: str) -> None:
    for label, prop in CONSTRAINTS:
        driver.execute_query(
            f"CREATE CONSTRAINT {label.lower()}_{prop} IF NOT EXISTS "
            f"FOR (n:{label}) REQUIRE n.{prop} IS UNIQUE",
            database_=db,
        )
    for label, prop in INDEXES:
        driver.execute_query(
            f"CREATE INDEX {label.lower()}_{prop} IF NOT EXISTS FOR (n:{label}) ON (n.{prop})",
            database_=db,
        )
    driver.execute_query("CALL db.awaitIndexes(300)", database_=db)


def load(driver: Driver, g: Graph, db: str = "neo4j", batch: int = 5000, log: Log = print) -> dict:
    t0 = time.time()
    wipe_facts(driver, db, log)
    ensure_schema(driver, db)

    def step(name: str, query: str, rows: list) -> None:
        t = time.time()
        n = _write(driver, db, query, rows, batch)
        log(f"{name:<22} {n:>9,}  {time.time() - t:6.1f} s")

    modules = sorted({f["module"] for f in g.files.values() if not f["external"]})
    step("Module", "UNWIND $rows AS r CREATE (:Module {name: r})", modules)
    step("File", "UNWIND $rows AS r CREATE (n:File) SET n = r", list(g.files.values()))

    by_label: dict[str, list[dict]] = defaultdict(list)
    for s in g.symbols.values():
        props = {k: v for k, v in s.items() if k != "label"}
        by_label[s["label"]].append(props)
    for label, rows in sorted(by_label.items()):
        step(f"Symbol:{label}", f"UNWIND $rows AS r CREATE (n:Symbol:{label}) SET n = r", rows)
    step(
        "Symbol:External",
        "UNWIND $rows AS r CREATE (n:Symbol:External) SET n = r, n.external = true",
        list(g.externals.values()),
    )
    for label, nodes in g.py.items():
        step(label, f"UNWIND $rows AS r CREATE (n:{label}) SET n = r", list(nodes.values()))

    for key, (rtype, a, b) in REL_SPECS.items():
        rows = g.rels.get(key, [])
        props = REL_PROPS.get(key, [])
        sets = " SET " + ", ".join(f"x.{p} = r.{p}" for p in props) if props else ""
        groups: dict[tuple, list] = defaultdict(list)
        for r in rows:
            groups[(r.get("la"), r.get("lb"))].append(r)
        for (la, lb), grp in sorted(groups.items(), key=lambda kv: str(kv[0])):
            ma, mb = (a.format(la=la, lb=lb), b.format(la=la, lb=lb)) if la else (a, b)
            q = f"UNWIND $rows AS r MATCH {ma} MATCH {mb} CREATE (a)-[x:{rtype}]->(b){sets}"
            step(f"-[{key}]->" + (f" {la}->{lb}" if la else ""), q, grp)

    run = g.run | {"loaded": datetime.now(UTC).isoformat(timespec="seconds")}
    run |= {f"n_{k.replace(' ', '_').replace(':', '_')}": v for k, v in g.counts().items()}
    driver.execute_query("CREATE (n:Run) SET n = $run", run=run, database_=db)
    total = time.time() - t0
    log(f"loaded in {total / 60:.1f} min")
    return run


def verify(driver: Driver, db: str = "neo4j") -> dict[str, int]:
    """Node counts per label and relationship counts per type, from the database."""
    out: dict[str, int] = {}
    recs, _, _ = driver.execute_query(
        "MATCH (n) UNWIND labels(n) AS l RETURN l, count(*) AS c ORDER BY l", database_=db
    )
    out |= {r["l"]: r["c"] for r in recs}
    recs, _, _ = driver.execute_query(
        "MATCH ()-[x]->() RETURN type(x) AS t, count(*) AS c ORDER BY t", database_=db
    )
    out |= {f"rel {r['t']}": r["c"] for r in recs}
    return out
