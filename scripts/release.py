"""Validate and push a prepared stable release to trigger GitHub Actions."""

import argparse
import subprocess

from prepare_release import ROOT, release_notes


def git(*args, check=True):
    return subprocess.run(
        ["git", *args], cwd=ROOT, check=check, text=True, capture_output=True
    )


def clean_checkout():
    if git("status", "--porcelain").stdout.strip():
        raise ValueError("Commit all checkout changes before releasing")


def release(version):
    tag = "v" + version.removeprefix("v")
    release_notes(tag)
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
    for command in ("check", "dist"):
        subprocess.run(["just", command], cwd=ROOT, check=True)
    clean_checkout()
    if (
        git("rev-parse", "HEAD").stdout.strip() != revision
        or git("symbolic-ref", "--quiet", "--short", "HEAD").stdout.strip() != branch
    ):
        raise ValueError("Branch or revision changed during release checks")
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
    parser.add_argument(
        "version", help="Stable version matching pyproject.toml, e.g. 0.1.0"
    )
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
