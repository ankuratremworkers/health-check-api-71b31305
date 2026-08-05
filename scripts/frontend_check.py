"""Are the frontend's declared dependencies actually installed?

`npm install` runs ONCE per workspace, before the first verify. Every package
the model adds to `package.json` after that point is declared and absent, and
the failure names the symptom rather than the cause:

    Cannot find package '@vitejs/plugin-react' imported from vite.config.ts
    error TS7016: Could not find a declaration file for module 'react-dom/client'
    sh: tsc: not found

Three messages, one cause: the manifest moved and node_modules did not. So this
re-installs whenever `package.json` has changed since the last install, and
then checks that what the manifest declares can actually be resolved — types
included, because `tsc` finds `@types/*` only in the project's own
node_modules, and a missing one surfaces as a type error in someone else's file.

Run from `frontend/`:  python ../scripts/frontend_check.py
"""

from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

FRONTEND = Path.cwd()
PKG = FRONTEND / "package.json"
MODULES = FRONTEND / "node_modules"
MARKER = MODULES / ".package-sha"

# Present in every stack template. If one of these is missing the build fails
# somewhere unrelated, so name them here where the message can be plain.
REQUIRED_BINS = ("tsc", "vite")


def fail(msg: str, detail: str = "") -> None:
    print(f"FAIL: {msg}", file=sys.stderr)
    if detail:
        print(detail.strip()[:4000], file=sys.stderr)
    sys.exit(1)


def manifest_sha() -> str:
    return hashlib.sha256(PKG.read_bytes()).hexdigest()


def npm(*args: str, timeout: int = 900) -> subprocess.CompletedProcess:
    # --include=dev because this runs with NODE_ENV=production, which npm reads
    # as omit=dev: no typescript, no vite, no @types/*.
    env = dict(os.environ, NODE_ENV="development")
    return subprocess.run(
        ["npm", *args, "--include=dev", "--no-audit", "--no-fund", "--legacy-peer-deps"],
        cwd=str(FRONTEND), capture_output=True, text=True, timeout=timeout, env=env,
    )


def ensure_installed() -> None:
    """Install when the manifest has moved since the last install."""
    sha = manifest_sha()
    if MODULES.is_dir() and MARKER.is_file() and MARKER.read_text().strip() == sha:
        print("deps: node_modules matches package.json")
        return

    why = "node_modules missing" if not MODULES.is_dir() else "package.json changed since install"
    print(f"deps: installing ({why})")
    res = npm("install")
    if res.returncode != 0:
        fail("npm install failed", (res.stderr or res.stdout))
    MODULES.mkdir(exist_ok=True)
    MARKER.write_text(sha, encoding="utf-8")
    print("deps: installed")


def check_declared_resolve() -> None:
    """Every dependency in the manifest must exist in node_modules.

    npm can exit 0 having skipped a package (a peer conflict under
    --legacy-peer-deps, an optional dependency for another platform), so a
    successful install is not evidence that the tree is complete.
    """
    manifest = json.loads(PKG.read_text(encoding="utf-8"))
    declared = {
        **manifest.get("dependencies", {}),
        **manifest.get("devDependencies", {}),
    }
    missing = [name for name in declared if not (MODULES / name).exists()]
    if missing:
        fail(
            "declared but not installed: " + ", ".join(sorted(missing)),
            "package.json lists these and node_modules does not have them. "
            "The build will fail on whichever one is imported first.",
        )
    print(f"deps: all {len(declared)} declared packages resolve")


def check_types_present() -> None:
    """@types/* for anything the project imports must be installed locally.

    tsc resolves @types ONLY from the project's own node_modules — a globally
    installed copy does not count, which is why "install typescript globally"
    never fixed TS7016.
    """
    manifest = json.loads(PKG.read_text(encoding="utf-8"))
    deps = {**manifest.get("dependencies", {}), **manifest.get("devDependencies", {})}
    types = [n for n in deps if n.startswith("@types/")]
    absent = [n for n in types if not (MODULES / n).exists()]
    if absent:
        fail("type packages declared but not installed: " + ", ".join(sorted(absent)))
    # react/react-dom without their types is the specific pairing that produces
    # TS7016 on `react-dom/client` — a message that names neither package.
    for lib in ("react", "react-dom"):
        if lib in deps and f"@types/{lib}" not in deps:
            fail(
                f"'{lib}' is a dependency but '@types/{lib}' is not declared",
                "tsc will report TS7016 against a file that did nothing wrong. "
                f"Add @types/{lib} to devDependencies.",
            )
    print(f"deps: {len(types)} type package(s) present")


def check_bins() -> None:
    """The toolchain the verify steps invoke must actually be runnable."""
    bindir = MODULES / ".bin"
    for name in REQUIRED_BINS:
        local = bindir / name
        if local.exists() or (local.with_suffix(".cmd")).exists() or shutil.which(name):
            continue
        fail(
            f"'{name}' is not runnable",
            f"Not in {bindir} and not on PATH. `npm run typecheck`/`build` will "
            f"fail with '{name}: not found', which reads as a broken script.",
        )
    print(f"deps: toolchain present ({', '.join(REQUIRED_BINS)})")


def main() -> None:
    if not PKG.is_file():
        print("no frontend/package.json — nothing to check")
        return
    ensure_installed()
    check_declared_resolve()
    check_types_present()
    check_bins()
    print("frontend dependency check: OK")


if __name__ == "__main__":
    main()
