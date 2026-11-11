"""Prepare, validate, commit, and push a stable release to trigger GitHub Actions."""

import argparse
import re
import subprocess
import tomllib
from datetime import date

from prepare_release import ROOT, release_notes


def git(*args, check=True):
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=check, text=True, capture_output=True
    )


def clean_checkout():
    if git("status", "--porcelain").stdout.strip():
        raise ValueError("Commit all checkout changes before releasing")


def prepare_source(version):
    project_path = ROOT / "pyproject.toml"
    source = project_path.read_text()
    current = tomllib.loads(source)["project"]["version"]
    changelog_path = ROOT / "CHANGELOG.md"
    changelog = changelog_path.read_text()
    dated = re.search(
        rf"^## {re.escape(version)} - \d{{4}}-\d{{2}}-\d{{2}}$", changelog, re.MULTILINE
    )
    if dated:
        if current != version:
            raise ValueError(f"Changelog already contains release {version}")
        release_notes(f"v{version}")
    else:
        section = re.search(
            r"^## Unreleased\n(.*?)(?=^## |\Z)", changelog, re.MULTILINE | re.DOTALL
        )
        if section is None or not section[1].strip():
            raise ValueError("Add release notes under ## Unreleased before releasing")
        changelog = (
            changelog[: section.start()]
            + f"## Unreleased\n\n## {version} - {date.today().isoformat()}\n"
            + section[1]
            + changelog[section.end() :]
        )
    # Restrict the replacement to the project table, leaving tool versions alone.
    project = re.search(r"(?ms)^\[project\]\n.*?(?=^\[|\Z)", source)
    updated, count = re.subn(
        r"(?m)^(version\s*=\s*)[\"'][^\"']+[\"']",
        lambda match: f'{match[1]}"{version}"',
        project[0],
    )
    if count != 1:
        raise ValueError("Expected one version assignment in [project]")
    project_path.write_text(
        source[: project.start()] + updated + source[project.end() :]
    )
    changelog_path.write_text(changelog)
    subprocess.run(["uv", "lock"], cwd=ROOT, check=True)
    release_notes(f"v{version}")


def release(version):
    tag = "v" + version.removeprefix("v")
    version = tag[1:]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Expected stable version MAJOR.MINOR.PATCH")
    clean_checkout()
    branch = git("symbolic-ref", "--quiet", "--short", "HEAD").stdout.strip()
    revision = git("rev-parse", "HEAD").stdout.strip()
    git("remote", "get-url", "origin")
    if (
        git(
            "show-ref", "--verify", "--quiet", f"refs/tags/{tag}", check=False
        ).returncode
        == 0
    ):
        raise ValueError(f"Local tag {tag} already exists")
    remote = git(
        "ls-remote", "--exit-code", "--tags", "origin", f"refs/tags/{tag}", check=False
    )
    if remote.returncode == 0:
        raise ValueError(f"Remote tag {tag} already exists")
    if remote.returncode != 2:
        raise ValueError(remote.stderr.strip() or "Could not query origin tags")
    prepare_source(version)
    for command in ("check", "dist"):
        subprocess.run(["just", command], cwd=ROOT, check=True)
    if (
        git("rev-parse", "HEAD").stdout.strip() != revision
        or git("symbolic-ref", "--quiet", "--short", "HEAD").stdout.strip() != branch
    ):
        raise ValueError("Branch or revision changed during release checks")
    changed = git("diff", "HEAD", "--name-only").stdout.splitlines()
    if (
        set(changed) - {"pyproject.toml", "uv.lock", "CHANGELOG.md"}
        or git("ls-files", "--others", "--exclude-standard").stdout.strip()
    ):
        raise ValueError("Unexpected checkout changes during release checks")
    if changed:
        git("add", "--", "pyproject.toml", "uv.lock", "CHANGELOG.md")
        git("commit", "-m", f"chore(release): {tag}")
    clean_checkout()
    revision = git("rev-parse", "HEAD").stdout.strip()
    git("tag", "--annotate", tag, "--message", f"Release {tag}", revision)
    try:
        git(
            "push",
            "--atomic",
            "origin",
            f"HEAD:refs/heads/{branch}",
            f"refs/tags/{tag}",
        )
    except subprocess.CalledProcessError as error:
        raise ValueError(
            f"Push failed; local tag {tag} remains. Resolve the failure and push "
            f"the branch and tag together, or delete the local tag before retrying.\n"
            f"{error.stderr}"
        ) from error
    print(
        f"Pushed {tag} and {branch}; GitHub Actions will verify and publish the release."
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("version", help="Stable version to release, e.g. 0.1.0")
    args = parser.parse_args()
    try:
        release(args.version)
    except (OSError, ValueError, subprocess.CalledProcessError) as error:
        detail = (
            error.stderr
            if isinstance(error, subprocess.CalledProcessError)
            else str(error)
        )
        parser.exit(1, f"Release failed: {detail}\n")
