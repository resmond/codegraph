"""Fact records shared by all extractors and the loader.

Every output file is JSON Lines; each line is one record with a type key ``t``.
Records are regenerable facts (decision §2): they can be deleted and rebuilt at any time.

Record types (schema 0.2):
  run       one per run: tool, versions, source revision, start time, settings
  tu        one per C++ translation unit: parse time, diagnostics, counts
  sym       a declaration or definition: usr, kind, name, qname, file, line range, flags
  edge      k = contains | inherits | calls | uses_type | includes | imports | overrides
            calls: n (call count) and sites (unique "file:line:col" of each call, max 200)
            overrides: method -> the base-class method it directly overrides (0.2)
  pymod / pyclass / pyfunc   Python module, class, function
  churn     per-file git statistics; cochange: file pair changed together
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import IO, Any

SCHEMA_VERSION = "0.2"

__all__ = ["SCHEMA_VERSION", "JsonlWriter", "dumps", "module_of"]


def module_of(rel: str) -> str:
    """Workbench or top-level area of a path relative to the FreeCAD checkout.

    src/Mod/Part/... -> Mod/Part, src/App/... -> App, build/.../src/Gui/... -> Gui,
    tests/... -> tests.
    """
    parts = rel.split("/")
    if parts[:2] == ["src", "Mod"] and len(parts) > 2:
        return "Mod/" + parts[2]
    if parts[0] == "src" and len(parts) > 1:
        return parts[1]
    if parts[0] == "build":
        try:
            i = parts.index("src")
            return module_of("/".join(parts[i:]))
        except ValueError:
            return "build"
    return parts[0]


def dumps(record: dict[str, Any]) -> str:
    return json.dumps(record, separators=(",", ":"), ensure_ascii=False)


class JsonlWriter:
    """Write records to ``path`` atomically: a ``.tmp`` file renamed on close."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.tmp = self.path.with_suffix(self.path.suffix + ".tmp")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._fh: IO[str] = self.tmp.open("w", encoding="utf-8")
        self.count = 0

    def write(self, record: dict[str, Any]) -> None:
        self._fh.write(dumps(record))
        self._fh.write("\n")
        self.count += 1

    def close(self) -> None:
        self._fh.close()
        self.tmp.replace(self.path)

    def abort(self) -> None:
        self._fh.close()
        self.tmp.unlink(missing_ok=True)

    def __enter__(self) -> JsonlWriter:
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        if exc_type is None:
            self.close()
        else:
            self.abort()
