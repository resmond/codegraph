# ruff: noqa: E501
import json
from pathlib import Path

from codegraph_store.model import build_graph


def _w(path: Path, recs: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("".join(json.dumps(r) + "\n" for r in recs))


def _sym(usr, file, line, d, kind="CXX_METHOD", **kw):
    return {
        "t": "sym",
        "usr": usr,
        "kind": kind,
        "name": usr,
        "qname": usr,
        "file": file,
        "line": line,
        "end": line + 5,
        "def": d,
        **kw,
    }


def make_run(tmp: Path) -> Path:
    run = tmp / "r1"
    _w(run / "runs.jsonl", [{"t": "run", "freecad_rev": "abc"}])
    # The same header symbols seen by two workers; definition in the .cpp.
    _w(
        run / "tus" / "a.jsonl",
        [
            _sym("C", "src/App/Doc.h", 10, True, kind="CLASS_DECL"),
            _sym("f", "src/App/Doc.h", 12, False, parent="C"),
            _sym("f", "src/App/Doc.cpp", 40, True, parent="C"),
            {"t": "metric", "usr": "f", "lines": 6, "cc": 3},
            {"t": "edge", "k": "calls", "src": "f", "dst": "ext::g", "dst_name": "std::g", "n": 2},
            {
                "t": "edge",
                "k": "inherits",
                "src": "C",
                "dst": "Base",
                "dst_name": "B",
                "access": "public",
            },
            {"t": "edge", "k": "includes", "src": "src/App/Doc.cpp", "dst": "src/App/Doc.h"},
            {"t": "tu", "file": "src/App/Doc.cpp", "errors": 0, "parse_s": 1.0},
        ],
    )
    _w(
        run / "tus" / "b.jsonl",
        [
            _sym("C", "src/App/Doc.h", 10, True, kind="CLASS_DECL"),
            _sym("f", "src/App/Doc.h", 12, False, parent="C"),
            {"t": "edge", "k": "calls", "src": "f", "dst": "ext::g", "dst_name": "std::g", "n": 3},
            {"t": "edge", "k": "includes", "src": "src/App/Doc.cpp", "dst": "src/App/Doc.h"},
            {"t": "tu", "file": "tests/src/App/T.cpp", "errors": 1, "parse_s": 1.0},
        ],
    )
    _w(
        run / "python.jsonl",
        [
            {"t": "pymod", "id": "Mod.Part.A", "file": "src/Mod/Part/A.py", "lines": 9, "doc": ""},
            {"t": "pymod", "id": "Mod.Part.B", "file": "src/Mod/Part/B.py", "lines": 9, "doc": ""},
            {
                "t": "pyclass",
                "id": "Mod.Part.A.K",
                "name": "K",
                "parent": "Mod.Part.A",
                "file": "src/Mod/Part/A.py",
                "line": 1,
                "end": 5,
                "bases": [],
            },
            {
                "t": "edge",
                "k": "imports",
                "src": "Mod.Part.A",
                "dst": ".B",
                "names": ["x"],
                "line": 1,
            },
            {
                "t": "edge",
                "k": "imports",
                "src": "Mod.Part.A",
                "dst": "Part.B",
                "names": ["y"],
                "line": 2,
            },
            {"t": "edge", "k": "imports", "src": "Mod.Part.A", "dst": "numpy", "line": 3},
        ],
    )
    _w(
        run / "git.jsonl",
        [
            {
                "t": "churn",
                "file": "src/App/Doc.cpp",
                "commits": 7,
                "added": 1,
                "deleted": 1,
                "first": 1,
                "last": 2,
                "authors": 2,
                "top_authors": ["a"],
            },
            {"t": "cochange", "a": "src/App/Doc.cpp", "b": "src/App/Doc.h", "n": 4},
        ],
    )
    return run


def test_dedup_and_locations(tmp_path):
    g = build_graph(make_run(tmp_path))
    assert set(g.symbols) == {"C", "f"}
    f = g.symbols["f"]
    assert (f["file"], f["line"], f["def"]) == ("src/App/Doc.cpp", 40, True)
    assert f["locs"] == ["src/App/Doc.cpp:40", "src/App/Doc.h:12"]
    assert (f["label"], f["cc"]) == ("Function", 3)
    assert g.rels["CONTAINS_SYM"] == [{"a": "C", "b": "f"}]


def test_edges_externals_and_includes(tmp_path):
    g = build_graph(make_run(tmp_path))
    assert g.rels["CALLS"] == [{"a": "f", "b": "ext::g", "n": 3}]  # max over TUs
    assert g.externals["ext::g"]["name"] == "std::g"
    assert g.rels["INHERITS"] == [{"a": "C", "b": "Base", "access": "public"}]
    assert g.rels["INCLUDES"] == [{"a": "src/App/Doc.cpp", "b": "src/App/Doc.h"}]


def test_files_modules_git(tmp_path):
    g = build_graph(make_run(tmp_path))
    doc = g.files["src/App/Doc.cpp"]
    assert (doc["module"], doc["lang"], doc["tu"], doc["commits"]) == ("App", "cpp", True, 7)
    t = g.files["tests/src/App/T.cpp"]
    assert t["test"] and t["module"] == "tests" and t["errors"] == 1
    assert g.notes["tu_errors"] == 1
    assert "test" not in g.symbols["f"]
    assert g.rels["CO_CHANGED"] == [{"a": "src/App/Doc.cpp", "b": "src/App/Doc.h", "n": 4}]


def test_python_imports(tmp_path):
    g = build_graph(make_run(tmp_path))
    imp = {r["b"]: r for r in g.rels["IMPORTS"]}
    assert imp["Mod.Part.B"]["names"] == ["x", "y"]  # relative + suffix import merge
    assert imp["numpy"]["how"] == "external" and imp["numpy"]["lb"] == "PyExternal"
    assert g.rels["PY_CONTAINS"] == [
        {"a": "Mod.Part.A", "b": "Mod.Part.A.K", "la": "PyModule", "lb": "PyClass"}
    ]
