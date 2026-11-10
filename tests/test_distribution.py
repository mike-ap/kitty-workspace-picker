"""Exercise the release artifact, rather than importing from the checkout."""

import io
import shutil
import subprocess
import sys
import tarfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
pytestmark = pytest.mark.skipif(
    shutil.which("kitty") is None, reason="Kitty is required for release verification"
)


@pytest.fixture(scope="module")
def archive(tmp_path_factory):
    output = tmp_path_factory.mktemp("distribution")
    result = subprocess.run(
        ["uv", "build", "--sdist", "--out-dir", str(output)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        timeout=60,
    )
    assert result.returncode == 0, result.stdout + result.stderr
    (archive,) = output.glob("*.tar.gz")
    return archive


def check(archive, cwd):
    return subprocess.run(
        [sys.executable, str(ROOT / "scripts/check_dist.py"), str(archive)],
        cwd=cwd,
        capture_output=True,
        text=True,
        timeout=60,
    )


def test_archive_installs_and_loads_under_kitty(archive, tmp_path):
    result = check(archive, tmp_path)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "isolated install, Kitty imports" in result.stdout


@pytest.mark.parametrize("damage", ["missing", "modified"])
def test_verification_rejects_incomplete_or_stale_archive(archive, tmp_path, damage):
    damaged = tmp_path / "damaged.tar.gz"
    with tarfile.open(archive) as source, tarfile.open(damaged, "w:gz") as target:
        endpoint = next(
            member.name
            for member in source.getmembers()
            if member.name.count("/") == 3
            and "/src/" in member.name
            and member.name.endswith(".py")
        )
        for member in source.getmembers():
            if member.name == endpoint:
                if damage == "missing":
                    continue
                content = b"# stale release file\n"
                member.size = len(content)
                target.addfile(member, io.BytesIO(content))
            else:
                target.addfile(
                    member, source.extractfile(member) if member.isfile() else None
                )
    result = check(damaged, tmp_path)
    assert result.returncode != 0
    assert endpoint.split("/", 1)[1] in result.stderr
    assert (
        "Missing archive file" if damage == "missing" else "does not match checkout"
    ) in result.stderr
