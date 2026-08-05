#!/usr/bin/env python
"""Actually import the backend, in a venv with its own pinned dependencies.

Every other backend check is static. `ruff` reads the file, `compileall` parses
it, and both pass on code that raises the moment it is imported — which is the
only failure mode that reaches production, because the platform reports a
deploy successful as soon as the container starts. A container that raises on
import then crash-loops while every status endpoint calls it healthy.

The failures this catches, all of which have shipped:

    assert not (status_code == 204 and response_model)   -- a 204 with a body
    ModuleNotFoundError: No module named 'email_validator'  -- EmailStr
    NameError                                            -- `del` at import scope
    ImportError                                          -- a route file that
                                                            imports a sibling
                                                            that does not exist

Dependency-light on purpose: stdlib only, so it runs wherever python does. The
venv lives at backend/.venv, which every snapshot and push already skips, and
is reused across runs — the install is skipped when the marker matches the
current requirements.txt.

Exit 1 with the real traceback on failure; that traceback IS the diagnostic.
"""

from __future__ import annotations

import hashlib
import os
import subprocess
import sys
import venv
from pathlib import Path

BACKEND = Path(__file__).resolve().parent.parent / "backend"
VENV = BACKEND / ".venv"
REQUIREMENTS = BACKEND / "requirements.txt"
MARKER = VENV / ".requirements-sha"
INSTALL_TIMEOUT = 600


def venv_python() -> Path:
    """The interpreter inside the venv, on either platform layout."""
    for rel in ("bin/python", "Scripts/python.exe"):
        candidate = VENV / rel
        if candidate.is_file():
            return candidate
    return VENV / "bin" / "python"


def ensure_env() -> Path:
    """Create the venv and install requirements, skipping if already current."""
    digest = ""
    if REQUIREMENTS.is_file():
        digest = hashlib.sha256(REQUIREMENTS.read_bytes()).hexdigest()

    if MARKER.is_file() and MARKER.read_text(encoding="utf-8").strip() == digest:
        return venv_python()

    if not venv_python().is_file():
        # with_pip: the venv needs its own pip to install into itself, and the
        # platform's pip cannot be pointed at another prefix reliably.
        venv.EnvBuilder(with_pip=True, clear=False).create(VENV)

    python = venv_python()
    if REQUIREMENTS.is_file():
        result = subprocess.run(
            [str(python), "-m", "pip", "install", "-q", "--disable-pip-version-check",
             "-r", str(REQUIREMENTS)],
            capture_output=True, text=True, timeout=INSTALL_TIMEOUT,
        )
        if result.returncode != 0:
            tail = (result.stderr or result.stdout or "").strip().splitlines()[-20:]
            print("installing backend dependencies FAILED:")
            print("\n".join(tail))
            print(
                "\nThis is requirements.txt, not the platform. A package name or "
                "version that does not exist fails here and fails identically in "
                "the deploy image."
            )
            raise SystemExit(1)
    MARKER.write_text(digest, encoding="utf-8")
    return python


#: Imported for its side effects — this is what uvicorn/gunicorn does to the
#: module in production, and the only thing that runs module-level code.
_IMPORT = """
import sys
sys.path.insert(0, {backend!r})
{body}
print("backend imports cleanly")
"""

_FASTAPI = """
import app.main
if not hasattr(app.main, "app"):
    print("app/main.py defines no `app` — uvicorn has nothing to serve")
    raise SystemExit(1)
"""

_DJANGO = """
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()
from django.core.management import call_command
call_command("check")
"""


def main() -> int:
    if not BACKEND.is_dir():
        print("no backend/ directory — nothing to import")
        return 0

    python = ensure_env()
    body = _DJANGO if (BACKEND / "manage.py").is_file() else _FASTAPI
    env = dict(os.environ)
    # A backend that reads DATABASE_URL at import must find something valid; a
    # throwaway sqlite file keeps the check about the code, not the database.
    # FORCED, not setdefault. This process inherits the PLATFORM's own
    # environment, where DATABASE_URL points at VibeCoder's Postgres — and
    # setdefault cannot override a value that is already there. The generated
    # app then opens a Postgres engine at import, and dies on
    # "ModuleNotFoundError: No module named 'psycopg2'" for a database it was
    # never meant to use. A generated app is verified against SQLite, always.
    env["DATABASE_URL"] = "sqlite:///./.venv/verify.db"
    env.setdefault("SECRET_KEY", "verify-only-not-a-secret")

    result = subprocess.run(
        [str(python), "-c", _IMPORT.format(backend=str(BACKEND), body=body)],
        cwd=str(BACKEND), capture_output=True, text=True, timeout=180, env=env,
    )
    sys.stdout.write(result.stdout)
    if result.returncode != 0:
        print("\nimporting the backend FAILED — it would crash-loop once deployed:")
        print((result.stderr or "").strip())
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
