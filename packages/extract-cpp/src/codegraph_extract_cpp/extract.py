"""Walk one translation unit and emit fact records for FreeCAD's own code.

Only cursors located in project files are walked (Boost, Qt, OpenCASCADE and the standard
library are skipped; calls into them are still recorded as edges to their USRs). Headers that
this worker process already walked are skipped too; the loader dedupes across workers.
"""

from __future__ import annotations

import time
from collections import Counter
from pathlib import Path

import clang.cindex as ci
from codegraph_schema import JsonlWriter, module_of

from .toolchain import Toolchain

K = ci.CursorKind

FUNCTION_KINDS = {
    K.FUNCTION_DECL,
    K.FUNCTION_TEMPLATE,
    K.CXX_METHOD,
    K.CONSTRUCTOR,
    K.DESTRUCTOR,
    K.CONVERSION_FUNCTION,
}
CLASS_KINDS = {
    K.CLASS_DECL,
    K.STRUCT_DECL,
    K.UNION_DECL,
    K.CLASS_TEMPLATE,
    K.CLASS_TEMPLATE_PARTIAL_SPECIALIZATION,
}
SYMBOL_KINDS = (
    FUNCTION_KINDS
    | CLASS_KINDS
    | {K.NAMESPACE, K.ENUM_DECL, K.FIELD_DECL, K.TYPEDEF_DECL, K.TYPE_ALIAS_DECL, K.VAR_DECL}
)
BRANCH_KINDS = {
    K.IF_STMT,
    K.FOR_STMT,
    K.CXX_FOR_RANGE_STMT,
    K.WHILE_STMT,
    K.DO_STMT,
    K.CASE_STMT,
    K.CONDITIONAL_OPERATOR,
    K.CXX_CATCH_STMT,
}
ACCESS = {
    ci.AccessSpecifier.PUBLIC: "public",
    ci.AccessSpecifier.PROTECTED: "protected",
    ci.AccessSpecifier.PRIVATE: "private",
}


def _kind(c: ci.Cursor):
    try:
        return c.kind
    except ValueError:  # a cursor kind newer than these bindings
        return None


def _qname(c: ci.Cursor) -> str:
    parts = []
    p = c
    while p is not None and _kind(p) not in (None, K.TRANSLATION_UNIT):
        if p.spelling:
            parts.append(p.spelling)
        p = p.semantic_parent
    return "::".join(reversed(parts))


class TuExtractor:
    def __init__(self, tc: Toolchain, index: ci.Index, base_args: list[str]) -> None:
        self.tc = tc
        self.index = index
        self.base_args = base_args
        self.done_headers: set[str] = set()  # headers already walked by this process
        self.seen_syms: set[tuple] = set()

    def run(self, entry: dict, out_path: Path) -> dict:
        main = entry["file"]
        t0 = time.perf_counter()
        tu = self.index.parse(
            main,
            args=self.base_args + entry["args"],
            options=ci.TranslationUnit.PARSE_DETAILED_PROCESSING_RECORD,
        )
        parse_s = time.perf_counter() - t0
        diags = [d for d in tu.diagnostics if d.severity >= ci.Diagnostic.Error]
        counts: Counter = Counter()
        walked_headers: set[str] = set()

        with JsonlWriter(out_path) as w:
            self.w, self.counts = w, counts
            for top in tu.cursor.get_children():
                f = top.location.file
                if f is None:
                    continue
                fname = f.name
                if not self.tc.is_project_file(fname):
                    continue
                if fname != main:
                    if fname in self.done_headers:
                        continue
                    walked_headers.add(fname)
                self._walk(top, ctx=None, cls=None)
            for inc in tu.get_includes():
                src, dst = inc.source.name, inc.include.name
                if self.tc.is_project_file(src):
                    w.write(
                        {
                            "t": "edge",
                            "k": "includes",
                            "src": self.tc.rel(src),
                            "dst": self.tc.rel(dst),
                            "project": self.tc.is_project_file(dst),
                        }
                    )
                    counts["includes"] += 1
            walk_s = time.perf_counter() - t0 - parse_s
            w.write(
                {
                    "t": "tu",
                    "file": self.tc.rel(main),
                    "module": module_of(self.tc.rel(main)),
                    "parse_s": round(parse_s, 2),
                    "walk_s": round(walk_s, 2),
                    "errors": len(diags),
                    "diag": [
                        f"{self.tc.rel(d.location.file.name) if d.location.file else '?'}:"
                        f"{d.location.line}: {d.spelling}"
                        for d in diags[:20]
                    ],
                    "counts": dict(counts),
                    "headers_walked": len(walked_headers),
                }
            )
        self.done_headers |= walked_headers
        return {
            "file": self.tc.rel(main),
            "parse_s": round(parse_s, 2),
            "walk_s": round(walk_s, 2),
            "errors": len(diags),
            "records": w.count,
        }

    # -- walking ---------------------------------------------------------------------------

    def _walk(self, root: ci.Cursor, ctx, cls) -> None:
        """Iterative pre-order walk. ctx = enclosing function state, cls = enclosing class USR."""
        stack = [(root, ctx, cls)]
        while stack:
            c, ctx, cls = stack.pop()
            kind = _kind(c)
            if kind is None:
                continue
            if kind in SYMBOL_KINDS and not (kind == K.VAR_DECL and ctx is not None):
                usr = self._symbol(c, kind, cls)
                if kind in FUNCTION_KINDS and c.is_definition():
                    fctx = {"usr": usr, "calls": Counter(), "types": set(), "cc": 1}
                    # LIFO: the marker goes first so it pops after the whole body.
                    stack.append((_FinishFunction(fctx, c), None, None))
                    self._push_children(stack, c, fctx, cls)
                    continue
                if kind in CLASS_KINDS:
                    self._push_children(stack, c, ctx, usr)
                    continue
            elif isinstance(c, _FinishFunction):
                self._finish_function(c)
                continue
            elif kind == K.CXX_BASE_SPECIFIER and cls:
                ref = c.referenced or c.type.get_declaration()
                busr = ref.get_usr() if ref is not None else ""
                if busr:
                    self.w.write(
                        {
                            "t": "edge",
                            "k": "inherits",
                            "src": cls,
                            "dst": busr,
                            "dst_name": _qname(ref),
                            "access": ACCESS.get(c.access_specifier, ""),
                        }
                    )
                    self.counts["inherits"] += 1
            elif ctx is not None:
                if kind == K.CALL_EXPR:
                    ref = c.referenced
                    if ref is not None:
                        rusr = ref.get_usr()
                        if rusr:
                            ctx["calls"][(rusr, _qname(ref))] += 1
                elif kind == K.TYPE_REF:
                    ref = c.referenced
                    if ref is not None and ref.get_usr():
                        ctx["types"].add(ref.get_usr())
                elif kind in BRANCH_KINDS:
                    ctx["cc"] += 1
                elif kind == K.BINARY_OPERATOR:
                    op = getattr(c, "binary_operator", None)
                    if op is not None and getattr(op, "name", "") in ("LAnd", "LOr"):
                        ctx["cc"] += 1
            self._push_children(stack, c, ctx, cls)

    @staticmethod
    def _push_children(stack, c, ctx, cls) -> None:
        children = list(c.get_children())
        for ch in reversed(children):
            stack.append((ch, ctx, cls))

    def _symbol(self, c: ci.Cursor, kind, cls) -> str:
        usr = c.get_usr()
        f = c.location.file
        fname = self.tc.rel(f.name) if f else ""
        key = (usr, fname, c.location.line, c.is_definition())
        if not usr or key in self.seen_syms:
            return usr
        self.seen_syms.add(key)
        rec = {
            "t": "sym",
            "usr": usr,
            "kind": kind.name,
            "name": c.spelling,
            "qname": _qname(c),
            "file": fname,
            "line": c.extent.start.line,
            "end": c.extent.end.line,
            "def": c.is_definition(),
        }
        parent = c.semantic_parent
        if parent is not None and _kind(parent) not in (None, K.TRANSLATION_UNIT):
            pusr = parent.get_usr()
            if pusr:
                rec["parent"] = pusr
        acc = ACCESS.get(c.access_specifier)
        if acc:
            rec["access"] = acc
        if kind in FUNCTION_KINDS:
            rec["sig"] = c.type.spelling
            if kind in (K.CXX_METHOD, K.DESTRUCTOR, K.CONVERSION_FUNCTION):
                flags = []
                if c.is_virtual_method():
                    flags.append("virtual")
                if c.is_pure_virtual_method():
                    flags.append("pure")
                if c.is_static_method():
                    flags.append("static")
                if c.is_const_method():
                    flags.append("const")
                if flags:
                    rec["flags"] = flags
        elif kind in (K.FIELD_DECL, K.VAR_DECL, K.TYPEDEF_DECL, K.TYPE_ALIAS_DECL):
            rec["type"] = c.type.spelling
        self.w.write(rec)
        self.counts[kind.name] += 1
        return usr

    def _finish_function(self, fin: _FinishFunction) -> None:
        ctx, c = fin.ctx, fin.cursor
        self.w.write(
            {
                "t": "metric",
                "usr": ctx["usr"],
                "lines": c.extent.end.line - c.extent.start.line + 1,
                "cc": ctx["cc"],
            }
        )
        for (dst, dname), n in ctx["calls"].items():
            self.w.write(
                {
                    "t": "edge",
                    "k": "calls",
                    "src": ctx["usr"],
                    "dst": dst,
                    "dst_name": dname,
                    "n": n,
                }
            )
        self.counts["calls"] += len(ctx["calls"])
        for dst in ctx["types"]:
            self.w.write({"t": "edge", "k": "uses_type", "src": ctx["usr"], "dst": dst})
        self.counts["uses_type"] += len(ctx["types"])


class _FinishFunction:
    """Stack marker: emit a function's metrics and edges after its body is walked."""

    __slots__ = ("ctx", "cursor")

    def __init__(self, ctx, cursor) -> None:
        self.ctx, self.cursor = ctx, cursor

    # Looks enough like a cursor for the walk loop's kind lookup.
    @property
    def kind(self):
        return K.UNEXPOSED_DECL

