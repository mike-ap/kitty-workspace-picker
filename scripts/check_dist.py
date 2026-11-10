"""Verify a source release by installing and importing it outside the checkout."""

import argparse
import os
import re
import shutil
import subprocess
import tarfile
import tomllib
from pathlib import Path
from tempfile import TemporaryDirectory

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    "install.sh",
    "bootstrap.sh",
    ".editorconfig",
    "lefthook.yml",
    ".github/workflows/check.yml",
    ".markdownlint-cli2.jsonc",
    ".github/workflows/release.yml",
    "README.md",
    "LICENSE",
    "CONTRIBUTING.md",
    "CHANGELOG.md",
    "pyproject.toml",
    "uv.lock",
    "justfile",
    ".python-version",
    "scripts/check_dist.py",
)
KITTY_CHECK = """
import importlib, runpy, subprocess, sys
from pathlib import Path

config = Path(sys.argv[1]).resolve()
package = sys.argv[2]
sys.path.insert(0, str(config))
module = importlib.import_module(package)
assert Path(module.__file__).resolve().parent == config / package
for name in sys.argv[3:]:
    namespace = runpy.run_path(str(config / name))
    if 'picker_module' in namespace:
        picker = namespace['picker_module'](str(config / name))
        assert Path(picker.__file__).resolve().parent == config / package
if package == 'kitty_workspaces':
    assert module.tab_bar.get_boss is not None
    command = module.runtime.collector_command(config / 'kitty_workspaces/worker.py')
    subprocess.run(command + ['--help'], check=True, capture_output=True, timeout=10)
"""


def run(command, *, cwd, env):
    result = subprocess.run(
        command, cwd=cwd, env=env, text=True, capture_output=True, timeout=30
    )
    if result.returncode:
        raise ValueError(f"{command[0]} failed:\n{result.stdout}{result.stderr}")


def verify(archive, kitty):
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    package = re.sub(r"[-_.]+", "_", project["name"])
    bundle_name = f"{package}-{project['version']}"
    with TemporaryDirectory(prefix="kitty-dist-check-") as temporary:
        directory = Path(temporary)
        with tarfile.open(archive, "r:gz") as bundle:
            if not bundle.getmembers() or any(
                member.name.split("/")[0] != bundle_name
                for member in bundle.getmembers()
            ):
                raise ValueError(f"Expected one archive directory named {bundle_name}")
            bundle.extractall(directory / "source", filter="data")
        source = directory / "source" / bundle_name
        expected = {ROOT / name for name in REQUIRED_FILES}
        for name in ("src", "scripts", "tests", "examples", "config", "docs"):
            expected.update(
                path
                for path in (ROOT / name).rglob("*")
                if path.is_file()
                and "__pycache__" not in path.parts
                and path.suffix not in {".pyc", ".pyo"}
            )
        for original in sorted(expected):
            relative = original.relative_to(ROOT)
            packaged = source / relative
            if not packaged.is_file():
                raise ValueError(f"Missing archive file: {relative}")
            if packaged.read_bytes() != original.read_bytes():
                raise ValueError(f"Archive does not match checkout: {relative}")

        config = directory / "config"
        config.mkdir()
        originals = {
            "kitty.conf": "# Existing configuration\n",
            "tab_bar.py": "def draw_title(data):\n    return data['title']\n",
        }
        for name, content in originals.items():
            (config / name).write_text(content)
        unrelated = directory / "unrelated"
        unrelated.mkdir()
        env = {
            key: value
            for key, value in os.environ.items()
            if not key.startswith("KITTY_") and key != "PYTHONPATH"
        }
        env["KITTY_CONFIG_DIRECTORY"] = str(config)
        run(["sh", str(source / "install.sh")], cwd=unrelated, env=env)
        for name, content in originals.items():
            if (config / name).read_text() != content:
                raise ValueError(f"Installer changed existing {name}")
        for original in (source / "src").rglob("*.py"):
            installed = config / original.relative_to(source / "src")
            if (
                not installed.is_file()
                or installed.read_bytes() != original.read_bytes()
            ):
                raise ValueError(
                    f"Missing or incorrect installed file: {installed.name}"
                )
        endpoints = [str(Path(package) / "kitten.py")]
        run(
            [kitty, "+runpy", KITTY_CHECK, str(config), package, *endpoints],
            cwd=unrelated,
            env=env,
        )
        marker = config / package / ("." + project["name"])
        if marker.read_text().splitlines() != [
            f"Installed by {project['name']}",
            f"version={project['version']}",
        ]:
            raise ValueError("Missing or incorrect installed version record")
        run(["sh", str(source / "install.sh"), "--uninstall"], cwd=unrelated, env=env)
        if list((config / package).glob("*.py")) or any(
            (config / name).exists() for name in endpoints
        ):
            raise ValueError("Uninstall left installed project files behind")
        for name, content in originals.items():
            if (config / name).read_text() != content:
                raise ValueError(f"Uninstall changed existing {name}")
    print(
        f"Verified {archive.name}: complete source, isolated install, Kitty imports, uninstall."
    )


def main():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    name = re.sub(r"[-_.]+", "_", project["name"])
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "archive",
        nargs="?",
        type=Path,
        default=ROOT / "dist" / f"{name}-{project['version']}.tar.gz",
    )
    args = parser.parse_args()
    kitty = shutil.which("kitty")
    if kitty is None:
        parser.error("Kitty must be on PATH to verify a release archive")
    try:
        verify(args.archive.resolve(), kitty)
    except (OSError, ValueError, tarfile.TarError, subprocess.SubprocessError) as error:
        parser.exit(1, f"Distribution check failed: {error}\n")


if __name__ == "__main__":
    main()
