#!/usr/bin/env python
"""House rules a compiler cannot check, checked anyway.

Every rule here is a mistake that COMPILES, ships, and then misbehaves — which
is exactly the set a linter and a type checker both miss. Knowing them is not
enough: a paragraph in a knowledge file gets followed most of the time, and the
times it doesn't are silent. So they run as part of verification.

Add a rule when a real build gets something wrong in a way that builds green.
Delete one when the template makes it impossible.

Exit code 1 with a report on any violation; no dependencies beyond the stdlib,
so it runs anywhere the project does.
"""

from __future__ import annotations

import ast
import re
import sys
from pathlib import Path
from typing import Iterator, List, NamedTuple

ROOT = Path(__file__).resolve().parent.parent

SKIP_DIRS = {
    "node_modules", ".venv", "venv", "__pycache__", ".git", "dist", "build",
    ".next", ".ruff_cache", ".mypy_cache", "staticfiles", "scripts",
}


class Violation(NamedTuple):
    path: Path
    line: int
    rule: str
    message: str

    def render(self) -> str:
        rel = self.path.relative_to(ROOT).as_posix()
        return f"{rel}:{self.line}: [{self.rule}] {self.message}"


def walk(*suffixes: str) -> Iterator[Path]:
    for path in ROOT.rglob("*"):
        if not path.is_file() or path.suffix not in suffixes:
            continue
        if any(part in SKIP_DIRS for part in path.relative_to(ROOT).parts):
            continue
        yield path


def lines_of(path: Path) -> List[str]:
    try:
        return path.read_text(encoding="utf-8").splitlines()
    except (UnicodeDecodeError, OSError):
        return []


# --------------------------------------------------------------------------- #
# Python
# --------------------------------------------------------------------------- #
_BCRYPT_HASH = re.compile(r"\bbcrypt\.(hashpw|checkpw)\s*\(")
_PASSLIB_BCRYPT = re.compile(r"CryptContext\s*\([^)]*bcrypt")
_PRE_HASH = re.compile(r"sha256|sha512|blake2|pre_?hash", re.IGNORECASE)


def check_python() -> Iterator[Violation]:
    for path in walk(".py"):
        lines = lines_of(path)
        body = "\n".join(lines)
        for i, line in enumerate(lines, start=1):
            # bcrypt silently TRUNCATES input past 72 bytes. A 100-character
            # password and its first 72 characters then authenticate the same
            # user, and nothing anywhere reports it.
            if _BCRYPT_HASH.search(line) and not _PRE_HASH.search(body):
                yield Violation(
                    path, i, "bcrypt-72",
                    "bcrypt truncates at 72 BYTES. Pre-hash the password "
                    "(e.g. base64(sha256(pw))) before bcrypt, or use argon2.",
                )
            if _PASSLIB_BCRYPT.search(line):
                yield Violation(
                    path, i, "passlib-bcrypt",
                    "passlib's bcrypt backend breaks against bcrypt>=4 (it reads "
                    "__about__.__version__). Use argon2, or bcrypt directly.",
                )
            if "EmailStr" in line and "email-validator" not in body:
                req = ROOT / "backend" / "requirements.txt"
                if req.is_file() and "email" not in req.read_text(encoding="utf-8"):
                    yield Violation(
                        path, i, "emailstr-dep",
                        "pydantic.EmailStr needs pydantic[email] / email-validator "
                        "in requirements.txt — it raises at import time without it.",
                    )

    req = ROOT / "backend" / "requirements.txt"
    if req.is_file():
        for i, line in enumerate(lines_of(req), start=1):
            bare = line.strip().lower()
            if bare.startswith("psycopg2") and not bare.startswith("psycopg2-binary"):
                yield Violation(
                    req, i, "psycopg2-binary",
                    "Bare psycopg2 builds from source and needs a C toolchain the "
                    "deploy image does not have. Use psycopg2-binary (or psycopg).",
                )


# --------------------------------------------------------------------------- #
# Frontend
# --------------------------------------------------------------------------- #
#: MUI v6/v7 dropped the shorthand system props. <Box mt={2}> compiles, renders,
#: and applies no margin — the worst kind of failure to debug.
_MUI_SHORTHAND = re.compile(
    r"<(?:Box|Stack|Typography|Paper|Grid|Container|Button)\b[^>]*?\s"
    r"(m|mt|mb|ml|mr|mx|my|p|pt|pb|pl|pr|px|py|bgcolor|color|width|height)="
    r"[{\"']"
)
_LOCALHOST = re.compile(r"['\"]https?://localhost:\d+")


def check_frontend() -> Iterator[Violation]:
    for path in walk(".tsx", ".ts", ".jsx", ".js"):
        for i, line in enumerate(lines_of(path), start=1):
            if _MUI_SHORTHAND.search(line):
                yield Violation(
                    path, i, "mui-sx-only",
                    "MUI v6+ ignores shorthand style props. Put it in sx: "
                    "sx={{ mt: 2 }}, not mt={2}.",
                )
            if _LOCALHOST.search(line) and path.name != "vite.config.ts":
                yield Violation(
                    path, i, "hardcoded-localhost",
                    "A hardcoded localhost URL works in dev and breaks the moment "
                    "it is deployed. Use the base URL from src/api.ts.",
                )


def _is_204(node: "ast.expr") -> bool:
    """Does this keyword value mean 204? Either the int or status.HTTP_204_*."""
    if isinstance(node, ast.Constant) and node.value == 204:
        return True
    return isinstance(node, ast.Attribute) and node.attr == "HTTP_204_NO_CONTENT"


def check_status_204() -> Iterator[Violation]:
    """A 204 route must not declare a response body — and `-> None` IS one.

    These route files start with `from __future__ import annotations` (PEP 563),
    so every annotation is a string. FastAPI resolves the return annotation into
    `response_model`, and for `-> None` that resolves to something truthy, so it
    asserts "Status code 204 must not have a response body" AT IMPORT — inside
    the container, after the platform has already called the deploy a success.

    Measured against fastapi 0.115.6, in a module with the future import:

        -> None        ASSERTS
        no annotation  OK
        -> Response    OK

    Without the future import `-> None` is fine, which is why this looks wrong
    until you check the top of the file. So the rule is: on a 204 route, write
    NO return annotation (or `-> Response`).

    `python -m compileall` cannot see any of this: the file compiles perfectly
    and nothing imports it until uvicorn does, in production.
    """
    for path in walk(".py"):
        try:
            source = path.read_text(encoding="utf-8")
            tree = ast.parse(source)
        except (OSError, SyntaxError):
            continue  # ruff and compileall both report this properly
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for deco in node.decorator_list:
                if not isinstance(deco, ast.Call):
                    continue
                kwargs = {k.arg: k.value for k in deco.keywords if k.arg}
                if "status_code" not in kwargs or not _is_204(kwargs["status_code"]):
                    continue
                if "response_model" in kwargs:
                    yield Violation(
                        path, deco.lineno, "204-no-body",
                        "A 204 route must not declare response_model. FastAPI "
                        "asserts this at import, crashing the deployed container.",
                    )
                elif node.returns is not None and ast.unparse(node.returns) != "Response":
                    shown = ast.unparse(node.returns)
                    yield Violation(
                        path, deco.lineno, "204-no-body",
                        f"A 204 handler annotated `-> {shown}` makes FastAPI infer a "
                        "response body and assert at import time. Write NO return "
                        "annotation on a 204 route (`-> None` counts, and fails too "
                        "because this file uses `from __future__ import annotations`).",
                    )


#: The Preview tab runs the frontend ALONE, in a browser sandbox with no
#: backend behind it. A screen whose data call goes straight to the network
#: renders "0 items" and an error there — which is the first thing anyone sees,
#: seconds after the build says it finished. Observed live: a reading-list app
#: that rendered its whole shell and then "0 books  500 Internal Server Error".
#:
#: The scaffold ships services/dataSource.ts for exactly this. An instruction
#: to use it was not enough — the model wrote its own client and bypassed it —
#: so it fails the build instead.
_BARE_FETCH = re.compile(r"\bfetch\s*\(")
_ALLOWED_FETCH_DIRS = ("services",)


def _frontend_src() -> Path:
    return ROOT / "frontend" / "src"


def check_preview_standalone() -> Iterator[Violation]:
    src = _frontend_src()
    if not src.is_dir():
        return

    ui_files = [
        p for p in src.rglob("*")
        if p.suffix in (".tsx", ".ts", ".jsx", ".js")
        and p.parent.name not in _ALLOWED_FETCH_DIRS
        and "services" not in p.relative_to(src).parts
    ]
    if not ui_files:
        return

    # 1. No component talks to the network directly.
    for path in ui_files:
        for i, line in enumerate(lines_of(path), start=1):
            if _BARE_FETCH.search(line):
                yield Violation(
                    path, i, "preview-bare-fetch",
                    "A direct fetch() renders nothing in the Preview tab, which "
                    "runs the frontend with no backend. Go through "
                    "services/dataSource.ts: "
                    "resolve(() => api.get('/api/x').then(r => r.data), SEED.x).",
                )

    # 2. If the app reads an API at all, it must have something to show first.
    text = chr(10).join(
        p.read_text(encoding="utf-8", errors="replace") for p in ui_files
    )
    uses_api = "resolve(" in text or "/api/" in text
    has_seed = (src / "services" / "mockData.ts").is_file()
    if uses_api and not has_seed:
        yield Violation(
            src, 1, "preview-no-seed",
            "This app reads an API but ships no seed data, so the Preview tab "
            "shows an empty screen. Call write_mock_data to generate "
            "services/mockData.ts, then pass those rows as the fallback to "
            "resolve(). Do not hand-write a seed module — it bypasses the "
            "resolver and never picks up the real API.",
        )

def main() -> int:
    violations = sorted(
        [*check_python(), *check_status_204(), *check_frontend(), *check_preview_standalone()],
        key=lambda v: (str(v.path), v.line),
    )
    if not violations:
        print("conventions: clean")
        return 0
    print(f"conventions: {len(violations)} violation(s)")
    for v in violations:
        print(v.render())
    return 1


if __name__ == "__main__":
    sys.exit(main())
