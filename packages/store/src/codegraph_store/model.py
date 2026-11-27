"""Turn a run directory's JSONL facts into deduplicated graph nodes and relationships.

Graph model (schema 0.1):

  (:Module {name})                      workbench / area: Mod/Part, App, Gui, tests ...
  (:File {path, module, lang, test, generated, external, tu, errors, commits, ...})
  (:Symbol:<Kind> {usr, kind, name, qname, file, line, end, def, sig, ...})
        Kind = Function | Class | Namespace | Field | Variable | Type | Enum
  (:Symbol:External {usr, name, external: true})   call/type/base targets outside FreeCAD
  (:PyModule|PyClass|PyFunc {id, ...}), (:PyExternal {id})   imports that don't resolve
  (:Run {id, ...})

  (Module)-[:CONTAINS]->(File)          (File)-[:INCLUDES]->(File)
  (Symbol)-[:DECLARED_IN]->(File)       (Symbol)-[:CONTAINS]->(Symbol)   parent -> member
  (Symbol)-[:CALLS {n, sites}]->(Symbol)   sites: "file:line:col" of each call (schema 0.2)
  (Symbol)-[:USES_TYPE]->(Symbol)       (Symbol)-[:INHERITS {access}]->(Symbol)
  (Symbol)-[:OVERRIDES]->(Symbol)       method -> base method it directly overrides (0.2)
  (File)-[:CO_CHANGED {n}]->(File)      git co-change, a < b
  (PyModule|PyClass)-[:CONTAINS]->(PyClass|PyFunc)   (PyModule)-[:DECLARED_IN]->(File)
  (PyModule)-[:IMPORTS {names, how}]->(PyModule|PyExternal)

Dedup: a C++ symbol repeats once per worker that walked its header; one node per USR. Its
location is the definition if there is one (else the first declaration, by path), and
``locs`` lists every distinct file:line. Edges dedupe on (kind, src, dst); ``calls.n`` is
the maximum over TUs (the same body walked twice reports the same count) and ``calls.sites``
the union of positions (capped at MAX_SITES).
"""

from __future__ import annotations

import json
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from codegraph_schema import module_of

KIND_LABEL = {
    "FUNCTION_DECL": "Function",
    "FUNCTION_TEMPLATE": "Function",
    "CXX_METHOD": "Function",
    "CONSTRUCTOR": "Function",
    "DESTRUCTOR": "Function",
    "CONVERSION_FUNCTION": "Function",
    "CLASS_DECL": "Class",
    "STRUCT_DECL": "Class",
    "UNION_DECL": "Class",
    "CLASS_TEMPLATE": "Class",
    "CLASS_TEMPLATE_PARTIAL_SPECIALIZATION": "Class",
    "NAMESPACE": "Namespace",
    "FIELD_DECL": "Field",
    "VAR_DECL": "Variable",
    "TYPEDEF_DECL": "Type",
    "TYPE_ALIAS_DECL": "Type",
    "ENUM_DECL": "Enum",
}
CPP_SUFFIXES = (".cpp", ".cxx", ".cc", ".c", ".h", ".hpp", ".hxx", ".inl")
MAX_SITES = 200
SYM_PROPS = ("kind", "name", "qname", "file", "line", "end", "def", "access", "sig", "type")


@dataclass
class Graph:
    run: dict[str, Any] = field(default_factory=dict)
    files: dict[str, dict] = field(default_factory=dict)
    symbols: dict[str, dict] = field(default_factory=dict)  # usr -> props (+ "label")
    externals: dict[str, dict] = field(default_factory=dict)  # usr -> {usr, name}
    rels: dict[str, list[dict]] = field(default_factory=lambda: defaultdict(list))
    py: dict[str, dict[str, dict]] = field(
        default_factory=lambda: {"PyModule": {}, "PyClass": {}, "PyFunc": {}, "PyExternal": {}}
    )
    notes: dict[str, int] = field(default_factory=lambda: defaultdict(int))

    def counts(self) -> dict[str, int]:
        c = {
            "File": len(self.files),
            "Module": len({f["module"] for f in self.files.values() if not f["external"]}),
            "Symbol": len(self.symbols),
            "Symbol:External": len(self.externals),
        }
        c |= {k: len(v) for k, v in self.py.items()}
        c |= {f"rel {k}": len(v) for k, v in sorted(self.rels.items())}
        return c


def _file(g: Graph, path: str) -> dict:
    f = g.files.get(path)
    if f is None:
        external = path.startswith("/")
        f = {
            "path": path,
            "module": "external" if external else module_of(path),
            "lang": "py"
            if path.endswith((".py", ".pyi"))
            else "cpp"
            if path.endswith(CPP_SUFFIXES)
            else "other",
            "test": path.startswith("tests/") or "/tests/" in path or "/Test" in path,
            "generated": path.startswith("build/"),
            "external": external,
        }
        g.files[path] = f
    return f


def _sym_rank(r: dict) -> tuple:
    """Lower is better: definitions first, then .cpp over headers, then path and line."""
    return (not r["def"], not r["file"].endswith((".cpp", ".cxx")), r["file"], r["line"])


def _usr_name(usr: str) -> str:
    """Readable fallback name for an external USR: the last named component."""
    for part in reversed(usr.split("@")):
        if part and part[0] not in "#>":
            return part.split("#")[0]
    return usr


def read_cpp(g: Graph, run: Path) -> None:
    best: dict[str, dict] = {}
    locs: dict[str, set[str]] = defaultdict(set)
    metric: dict[str, dict] = {}
    parents: dict[str, str] = {}
    edges: dict[tuple[str, str, str], dict] = {}
    includes: set[tuple[str, str]] = set()
    for p in sorted((run / "tus").glob("*.jsonl")):
        with p.open(encoding="utf-8") as fh:
            for line in fh:
                r = json.loads(line)
                t = r["t"]
                if t == "sym":
                    usr = r["usr"]
                    locs[usr].add(f"{r['file']}:{r['line']}")
                    if usr not in best or _sym_rank(r) < _sym_rank(best[usr]):
                        best[usr] = r
                    if "parent" in r:
                        parents.setdefault(usr, r["parent"])
                elif t == "edge":
                    k = r["k"]
                    if k == "includes":
                        includes.add((r["src"], r["dst"]))
                        continue
                    key = (k, r["src"], r["dst"])
                    e = edges.get(key)
                    if e is None:
                        edges[key] = r
                    elif k == "calls":
                        e["n"] = max(e["n"], r["n"])
                        if r.get("sites"):
                            e["sites"] = list(dict.fromkeys([*e.get("sites", []), *r["sites"]]))
                elif t == "metric":
                    m = metric.get(r["usr"])
                    if m is None or r["lines"] > m["lines"]:
                        metric[r["usr"]] = r
                elif t == "tu":
                    f = _file(g, r["file"])
                    f |= {"tu": True, "errors": r["errors"], "parse_s": r["parse_s"]}
                    g.notes["tu"] += 1
                    g.notes["tu_errors"] += r["errors"] > 0

    for usr, r in best.items():
        s = {k: r[k] for k in SYM_PROPS if k in r}
        s["usr"] = usr
        s["label"] = KIND_LABEL.get(r["kind"], "Other")
        if "flags" in r:
            s["flags"] = r["flags"]
        if s["file"].startswith("tests/"):
            s["test"] = True
        if len(locs[usr]) > 1:
            s["locs"] = sorted(locs[usr])
        if usr in metric:
            s["lines"], s["cc"] = metric[usr]["lines"], metric[usr]["cc"]
        g.symbols[usr] = s
        if s["file"]:
            _file(g, s["file"])
            g.rels["DECLARED_IN"].append({"a": usr, "b": s["file"]})

    for usr, parent in parents.items():
        if parent in g.symbols:
            g.rels["CONTAINS_SYM"].append({"a": parent, "b": usr})
        else:
            g.notes["parent_not_project"] += 1

    rel_type = {
        "calls": "CALLS",
        "uses_type": "USES_TYPE",
        "inherits": "INHERITS",
        "overrides": "OVERRIDES",
    }
    for (k, src, dst), r in edges.items():
        if src not in g.symbols:
            g.notes[f"{k}_src_missing"] += 1
            continue
        if dst not in g.symbols and dst not in g.externals:
            g.externals[dst] = {"usr": dst, "name": r.get("dst_name") or _usr_name(dst)}
        row: dict[str, Any] = {"a": src, "b": dst}
        if k == "calls":
            row["n"] = r["n"]
            if r.get("sites"):
                row["sites"] = sorted(r["sites"])[:MAX_SITES]
        elif k == "inherits":
            row["access"] = r.get("access", "")
        g.rels[rel_type[k]].append(row)

    for src, dst in includes:
        _file(g, src)
        _file(g, dst)
        g.rels["INCLUDES"].append({"a": src, "b": dst})


def read_python(g: Graph, path: Path) -> None:
    if not path.exists():
        g.notes["python_missing"] += 1
        return
    imports = []
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            t = r["t"]
            if t == "pymod":
                g.py["PyModule"][r["id"]] = {k: r[k] for k in ("id", "file", "lines", "doc")}
                _file(g, r["file"])
                g.rels["PY_DECLARED_IN"].append({"a": r["id"], "b": r["file"]})
            elif t in ("pyclass", "pyfunc"):
                label = "PyClass" if t == "pyclass" else "PyFunc"
                props = {k: v for k, v in r.items() if k not in ("t", "parent")}
                g.py[label][r["id"]] = props
                g.rels["PY_CONTAINS"].append({"a": r["parent"], "b": r["id"]})
            elif t == "edge" and r["k"] == "imports":
                imports.append(r)
            elif t == "pyerror":
                g.notes["py_parse_errors"] += 1

    mods = g.py["PyModule"]
    by_suffix: dict[str, list[str]] = defaultdict(list)
    for mid in mods:
        parts = mid.split(".")
        for i in range(len(parts)):
            by_suffix[".".join(parts[i:])].append(mid)

    seen: dict[tuple[str, str], dict] = {}
    for r in imports:
        src, dst = r["src"], r["dst"]
        if dst.startswith("."):  # relative: from .x import y / from .. import z
            level = len(dst) - len(dst.lstrip("."))
            base = src.split(".")[:-level]
            dst = ".".join([*base, dst.lstrip(".")] if dst.lstrip(".") else base)
        if dst in mods:
            target, how = dst, "exact"
        elif len(by_suffix.get(dst, [])) == 1:
            target, how = by_suffix[dst][0], "suffix"
        else:
            target, how = dst, "external"
            g.py["PyExternal"].setdefault(dst, {"id": dst})
        key = (src, target)
        if key in seen:
            seen[key]["names"] = sorted(set(seen[key]["names"]) | set(r.get("names", [])))
            continue
        seen[key] = {"a": src, "b": target, "how": how, "names": sorted(set(r.get("names", [])))}
    g.rels["IMPORTS"] = list(seen.values())

    # Label each Python endpoint so the loader can match it by an indexed label.
    label_of = {i: label for label, nodes in g.py.items() for i in nodes}
    rows = []
    for r in g.rels["PY_CONTAINS"]:
        la, lb = label_of.get(r["a"]), label_of.get(r["b"])
        if la and lb:
            rows.append(r | {"la": la, "lb": lb})
        else:
            g.notes["py_parent_missing"] += 1
    g.rels["PY_CONTAINS"] = rows
    for r in g.rels["IMPORTS"]:
        r["la"], r["lb"] = "PyModule", label_of[r["b"]]


def read_git(g: Graph, path: Path) -> None:
    if not path.exists():
        g.notes["git_missing"] += 1
        return
    with path.open(encoding="utf-8") as fh:
        for line in fh:
            r = json.loads(line)
            if r["t"] == "churn":
                f = _file(g, r["file"])
                f |= {k: r[k] for k in ("commits", "added", "deleted", "first", "last", "authors")}
                f["top_authors"] = r.get("top_authors", [])
            elif r["t"] == "cochange":
                _file(g, r["a"])
                _file(g, r["b"])
                g.rels["CO_CHANGED"].append({"a": r["a"], "b": r["b"], "n": r["n"]})


def build_graph(run: Path) -> Graph:
    run = Path(run).expanduser()
    g = Graph()
    runs = [json.loads(x) for x in (run / "runs.jsonl").read_text().splitlines() if x.strip()]
    last = runs[-1] if runs else {}
    g.run = {
        "id": run.name,
        "freecad_rev": last.get("freecad_rev", ""),
        "compiler": last.get("compiler", ""),
        "libclang": last.get("libclang", ""),
        "parsed": last.get("started", ""),
    }
    read_cpp(g, run)
    read_python(g, run / "python.jsonl")
    read_git(g, run / "git.jsonl")
    for f in g.files.values():
        if not f["external"]:
            g.rels["MODULE_CONTAINS"].append({"a": f["module"], "b": f["path"]})
    return g
