"""FreeCAD's own pixi toolchain for libclang: exact compiler match (docs/status.md).

libclang ignores the conda compiler's ``.cfg`` include setup, so we pass ``-nostdinc
-nostdinc++`` and then ``-isystem`` for every path the real ``clang++`` searches.
"""

from __future__ import annotations

import json
import shlex
import subprocess
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class Toolchain:
    freecad: Path  # ~/src/FreeCAD
    build: Path  # ~/src/FreeCAD/build/release

    @property
    def env(self) -> Path:
        return self.freecad / ".pixi" / "envs" / "default"

    @property
    def libclang(self) -> Path:
        return self.env / "lib" / "libclang.so.13"

    @property
    def clangxx(self) -> Path:
        return self.env / "bin" / "clang++"

    @property
    def resource_dir(self) -> Path:
        out = subprocess.run(
            [str(self.clangxx), "-print-resource-dir"], capture_output=True, text=True, check=True
        )
        return Path(out.stdout.strip())

    @property
    def compile_db(self) -> Path:
        return self.build / "compile_commands.json"

    def version(self) -> str:
        out = subprocess.run([str(self.clangxx), "--version"], capture_output=True, text=True)
        return out.stdout.splitlines()[0] if out.stdout else "unknown"

    def base_args(self) -> list[str]:
        """Flags that reproduce the compiler's own include search order."""
        out = subprocess.run(
            [str(self.clangxx), "-E", "-x", "c++", "-", "-v"],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
        ).stderr
        inc = out.split("#include <...> search starts here:")[1].split("End of search list.")[0]
        args = ["-nostdinc", "-nostdinc++", "-resource-dir", str(self.resource_dir)]
        for d in inc.split():
            args += ["-isystem", d]
        return args

    def is_project_file(self, path: str) -> bool:
        """FreeCAD's own code: src/ (minus vendored 3rdParty) and generated files in build/."""
        src = str(self.freecad / "src") + "/"
        if path.startswith(src):
            return not path.startswith(src + "3rdParty/")
        return path.startswith(str(self.build) + "/") and "/3rdParty/" not in path

    def skip_tu(self, path: str) -> bool:
        """Whole TUs that aren't FreeCAD's own code: vendored 3rdParty sources (also when built
        into build/), Qt resource data (qrc_*) and Qt meta-object code (moc_*, automoc)."""
        name = path.rsplit("/", 1)[-1]
        return (
            "/3rdParty/" in path
            or name.startswith(("qrc_", "moc_"))
            or name == "mocs_compilation.cpp"
        )

    def rel(self, path: str) -> str:
        """Path relative to the FreeCAD checkout (build files keep their build/... prefix)."""
        root = str(self.freecad) + "/"
        return path[len(root) :] if path.startswith(root) else path


def load_compile_db(tc: Toolchain) -> list[dict]:
    """Entries with ``file`` and cleaned ``args`` (no compiler, -c, -o, or the source itself)."""
    entries = []
    for e in json.loads(tc.compile_db.read_text()):
        raw = e.get("arguments") or shlex.split(e["command"])
        args, skip = [], False
        for a in raw[1:]:
            if skip:
                skip = False
                continue
            if a == "-o":
                skip = True
                continue
            if a == "-c" or a == e["file"]:
                continue
            args.append(a)
        entries.append({"file": e["file"], "dir": e.get("directory", ""), "args": args})
    return entries
