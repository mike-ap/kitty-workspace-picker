"""Stage verified source and a version-pinned bootstrap for a GitHub release."""

import argparse
import hashlib
import re
import shutil
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def release_notes(tag):
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    version = project["version"]
    if not re.fullmatch(r"\d+\.\d+\.\d+", version) or tag != f"v{version}":
        raise ValueError(
            "Stable release tag must match pyproject.toml (vMAJOR.MINOR.PATCH)"
        )
    changelog = (ROOT / "CHANGELOG.md").read_text()
    section = re.search(
        rf"^## {re.escape(version)} - \d{{4}}-\d{{2}}-\d{{2}}\n(.*?)(?=^## |\Z)",
        changelog,
        re.MULTILINE | re.DOTALL,
    )
    if section is None or not section[1].strip():
        raise ValueError("Add a dated CHANGELOG section: ## VERSION - YYYY-MM-DD")
    return project, section[1].strip() + "\n"


def prepare(tag, repository):
    project, notes = release_notes(tag)
    version = project["version"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Expected GitHub OWNER/REPO")
    source = ROOT / "dist" / f"{project['name'].replace('-', '_')}-{version}.tar.gz"
    destination = ROOT / "dist/release"
    destination.mkdir(parents=True, exist_ok=True)
    archive = destination / f"{project['name']}.tar.gz"
    shutil.copyfile(source, archive)
    bootstrap = (ROOT / "bootstrap.sh").read_text()
    (destination / "bootstrap.sh").write_text(
        bootstrap.replace("@REPOSITORY@", repository).replace("@TAG@", tag)
    )
    (destination / "SHA256SUMS").write_text(
        f"{hashlib.sha256(archive.read_bytes()).hexdigest()}  {archive.name}\n"
    )
    (destination / "notes.md").write_text(notes)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("tag")
    parser.add_argument("repository")
    args = parser.parse_args()
    try:
        prepare(args.tag, args.repository)
    except (OSError, ValueError) as error:
        parser.exit(1, f"Release preparation failed: {error}\n")
