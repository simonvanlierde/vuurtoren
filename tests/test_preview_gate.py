"""Preview credentials are usable only for a non-fork with both values present."""

import subprocess
from pathlib import Path

import pytest

_SCRIPT = Path(__file__).resolve().parent.parent / ".github/scripts/cloudflare-gate.sh"


@pytest.mark.parametrize(
    ("token", "account", "fork", "allowed"),
    [
        ("", "", "false", False),
        ("example-token", "", "false", False),
        ("", "example-account", "false", False),
        ("example-token", "example-account", "true", False),
        ("example-token", "example-account", "false", True),
    ],
)
def test_preview_requires_credentials_and_non_fork(
    tmp_path: Path,
    token: str,
    account: str,
    fork: str,
    *,
    allowed: bool,
) -> None:
    """A fork must skip even if the job accidentally supplies credentials."""
    output = tmp_path / "output"
    subprocess.run(  # noqa: S603  # repository script, isolated synthetic environment
        ["/bin/bash", str(_SCRIPT), "Preview"],
        env={"TOKEN": token, "ACCOUNT": account, "FORK": fork, "GITHUB_OUTPUT": str(output)},
        check=True,
        capture_output=True,
        text=True,
        timeout=5,
    )
    assert output.read_text() == f"run={str(allowed).lower()}\n"
