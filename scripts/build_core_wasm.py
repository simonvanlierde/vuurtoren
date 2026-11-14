"""Build the core for the installed Pyodide runtime inside its declared SDK container."""

import json
import os
import shutil
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    """Build without installing an SDK or Rust target on the host."""
    package = json.loads((ROOT / "frontend/node_modules/pyodide/package.json").read_text())
    version = package["version"]
    docker = shutil.which("docker")
    if docker is None:
        msg = "Docker is required for the Pyodide cross-build"
        raise RuntimeError(msg)
    project = tomllib.loads((ROOT / "core/pyproject.toml").read_text())
    build_spec = next(
        s for s in project["dependency-groups"]["build"] if s.startswith("pyodide-build")
    )
    subprocess.run(  # noqa: S603  # fixed project build command
        [docker, "build", "-f", "core/Dockerfile", "-t", "vuurtoren-core-build:local", "."],
        cwd=ROOT,
        check=True,
    )
    subprocess.run(  # noqa: S603  # project paths and installed dependency metadata
        [
            docker,
            "run",
            "--rm",
            "--name",
            "tmp-vuurtoren-core-build",
            "--user",
            f"{os.getuid()}:{os.getgid()}",
            "-e",
            "HOME=/tmp",
            "-e",
            "UV_CACHE_DIR=/work/core/.cache/uv",
            "-e",
            "CARGO_HOME=/work/core/.cache/cargo",
            "-e",
            "CARGO_TARGET_DIR=/work/core/target-wasm",
            "-e",
            "PYODIDE_XBUILDENV_PATH=/work/core/.pyodide-xbuildenv",
            "-v",
            f"{ROOT}:/work",
            "-w",
            "/work",
            "vuurtoren-core-build:local",
            "sh",
            "-c",
            (
                'uv run --no-project --python 3.14 --with "$1" pyodide xbuildenv install "$2" '
                '&& uv run --no-project --python 3.14 --with "$1" '
                "pyodide build core -o dist/pyodide"
            ),
            "sh",
            build_spec,
            version,
        ],
        cwd=ROOT,
        check=True,
    )


if __name__ == "__main__":
    main()
