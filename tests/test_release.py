"""Exercise release pushes against a disposable local Git remote."""

import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]


def git(root, *args):
    return subprocess.run(
        ["git", "-C", str(root), *args], check=True, text=True, capture_output=True
    ).stdout.strip()


@pytest.fixture
def checkout(tmp_path):
    root = tmp_path / "checkout"
    root.mkdir()
    git(root, "init", "--initial-branch=main")
    git(root, "config", "user.name", "Release Test")
    git(root, "config", "user.email", "release@example.invalid")
    git(root, "config", "commit.gpgsign", "false")
    git(root, "config", "tag.gpgsign", "false")
    git(root, "config", "core.hooksPath", str(tmp_path / "no-hooks"))
    (root / "scripts").mkdir()
    for name in ("release.py", "prepare_release.py"):
        shutil.copy2(ROOT / "scripts" / name, root / "scripts" / name)
    (root / ".gitignore").write_text("__pycache__/\n")
    (root / "pyproject.toml").write_text('[project]\nversion = "0.1.0"\n')
    (root / "CHANGELOG.md").write_text("## 0.1.0 - 2026-11-04\n\nInitial release.\n")
    git(root, "add", ".")
    git(root, "commit", "-m", "Initial source")
    remote = tmp_path / "remote.git"
    subprocess.run(
        ["git", "init", "--bare", str(remote)], check=True, capture_output=True
    )
    git(root, "remote", "add", "origin", str(remote))
    binary = tmp_path / "bin"
    binary.mkdir()
    just = binary / "just"
    just.write_text(
        f"#!{sys.executable}\n"
        "import os, sys\n"
        "with open(os.environ['CHECK_LOG'], 'a') as log: log.write(sys.argv[1] + '\\n')\n"
        "sys.exit(1 if os.environ.get('FAIL_CHECK') == sys.argv[1] else 0)\n"
    )
    just.chmod(0o755)
    env = os.environ | {
        "PATH": str(binary) + os.pathsep + os.environ["PATH"],
        "CHECK_LOG": str(tmp_path / "checks"),
    }
    return root, remote, env


def release(checkout, version="0.1.0"):
    root, _, env = checkout
    return subprocess.run(
        [sys.executable, str(root / "scripts/release.py"), version],
        env=env,
        text=True,
        capture_output=True,
        timeout=20,
    )


def test_release_checks_then_pushes_branch_and_annotated_tag(checkout):
    root, remote, env = checkout
    result = release(checkout)
    assert result.returncode == 0, result.stderr
    assert Path(env["CHECK_LOG"]).read_text().splitlines() == ["check", "dist"]
    assert git(root, "cat-file", "-t", "v0.1.0") == "tag"
    assert git(remote, "rev-parse", "refs/heads/main") == git(root, "rev-parse", "HEAD")
    assert git(remote, "rev-parse", "refs/tags/v0.1.0") == git(
        root, "rev-parse", "v0.1.0"
    )


@pytest.mark.parametrize(
    "problem", ["dirty", "version", "local-tag", "remote-tag", "check"]
)
def test_failed_preflight_never_pushes_a_branch(checkout, problem):
    root, remote, env = checkout
    if problem == "dirty":
        (root / "uncommitted").write_text("pending")
    elif problem in ("local-tag", "remote-tag"):
        git(root, "tag", "v0.1.0")
        if problem == "remote-tag":
            git(root, "push", "origin", "refs/tags/v0.1.0")
            git(root, "tag", "--delete", "v0.1.0")
    elif problem == "check":
        env["FAIL_CHECK"] = "check"
    result = release(checkout, "9.9.9" if problem == "version" else "0.1.0")
    assert result.returncode != 0
    assert not git(remote, "for-each-ref", "refs/heads")
    if problem != "local-tag":
        assert not git(root, "tag", "--list")


def test_rejected_push_keeps_local_tag_and_reports_recovery(checkout):
    root, remote, _ = checkout
    reject = remote / "hooks/pre-receive"
    reject.write_text("#!/bin/sh\nexit 1\n")
    reject.chmod(0o755)
    result = release(checkout)
    assert result.returncode != 0
    assert "local tag v0.1.0 remains" in result.stderr
    assert git(root, "tag", "--list") == "v0.1.0"
    assert not git(remote, "for-each-ref")
