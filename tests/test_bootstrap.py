"""Install staged release assets through the piped-shell entry point, offline."""

import os
import runpy
import shutil
import subprocess
import sys
import tarfile
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
PACKAGE = PROJECT["name"].replace("-", "_")


@pytest.fixture
def release(tmp_path, monkeypatch):
    root = tmp_path / "release source"
    source = root / "source" / f"{PACKAGE}-0.1.0"
    source.mkdir(parents=True)
    for name in ("install.sh", "bootstrap.sh", "pyproject.toml"):
        shutil.copy2(ROOT / name, source / name)
        shutil.copy2(ROOT / name, root / name)
    # Keep the fixture independent of the project's next release version.
    for metadata in (root / "pyproject.toml", source / "pyproject.toml"):
        metadata.write_text(
            metadata.read_text().replace(
                f'version = "{PROJECT["version"]}"', 'version = "0.1.0"'
            )
        )
    for name in ("src", "config"):
        shutil.copytree(ROOT / name, source / name)
    (root / "CHANGELOG.md").write_text("## 0.1.0 - 2026-11-04\n\nInitial release.\n")
    (root / "dist").mkdir()
    with tarfile.open(root / "dist" / f"{PACKAGE}-0.1.0.tar.gz", "w:gz") as archive:
        archive.add(source, arcname=source.name)
    namespace = runpy.run_path(str(ROOT / "scripts/prepare_release.py"))
    prepare = namespace["prepare"]
    monkeypatch.setitem(prepare.__globals__, "ROOT", root)
    prepare("v0.1.0", f"example/{PROJECT['name']}")
    assets = root / "dist/release"
    binary = tmp_path / "bin"
    binary.mkdir()
    curl = binary / "curl"
    curl.write_text(
        f"#!{sys.executable}\n"
        "import os, pathlib, shutil, sys\n"
        "args = sys.argv[1:]\n"
        "url = args[args.index('-o') - 1]\n"
        "with open(os.environ['CURL_LOG'], 'a') as log: log.write(url + '\\n')\n"
        "shutil.copyfile(pathlib.Path(os.environ['ASSETS']) / url.rsplit('/', 1)[1], "
        "args[args.index('-o') + 1])\n"
    )
    curl.chmod(0o755)
    env = os.environ | {
        "PATH": str(binary) + os.pathsep + os.environ["PATH"],
        "ASSETS": str(assets),
        "CURL_LOG": str(tmp_path / "requests"),
        "TMPDIR": str(tmp_path),
    }
    return assets, env, prepare


def run_bootstrap(release, config, *arguments):
    assets, env, _ = release
    return subprocess.run(
        ["sh", "-s", "--", "--config-dir", str(config), *arguments],
        input=(assets / "bootstrap.sh").read_text(),
        text=True,
        capture_output=True,
        env=env,
        timeout=20,
    )


@pytest.mark.parametrize("explicit_version", [False, True])
def test_piped_bootstrap_installs_updates_and_uninstalls(
    release, tmp_path, explicit_version
):
    config = tmp_path / "kitty config"
    config.mkdir()
    (config / "kitty.conf").write_text("# existing configuration\n")
    arguments = ("--version", "0.1.0") if explicit_version else ()
    result = run_bootstrap(release, config, *arguments)
    assert result.returncode == 0, result.stderr
    assert (config / PACKAGE / "__init__.py").is_file()
    assert (
        (config / PACKAGE / ("." + PROJECT["name"]))
        .read_text()
        .endswith("version=0.1.0\n")
    )
    example = config / PACKAGE / (PROJECT["name"] + ".conf")
    assert not example.exists()
    example.write_text("# user edits\n")
    assert run_bootstrap(release, config).returncode == 0
    assert example.read_text() == "# user edits\n"
    assert run_bootstrap(release, config, "--uninstall").returncode == 0
    assert not list((config / PACKAGE).glob("*.py"))
    assert example.read_text() == "# user edits\n"
    assert (config / "kitty.conf").read_text() == "# existing configuration\n"
    requests = Path(release[1]["CURL_LOG"]).read_text().splitlines()
    assert all(
        f"/example/{PROJECT['name']}/releases/download/v0.1.0/" in url
        for url in requests
    )
    assert not list(tmp_path.glob(f"{PROJECT['name']}-install.*"))


def test_bad_checksum_never_touches_configuration(release, tmp_path):
    assets, _, _ = release
    (assets / f"{PROJECT['name']}.tar.gz").write_bytes(b"corrupt")
    config = tmp_path / "kitty"
    result = run_bootstrap(release, config)
    assert result.returncode != 0
    assert "checksum mismatch" in result.stderr
    assert not config.exists()
    assert not list(tmp_path.glob(f"{PROJECT['name']}-install.*"))


@pytest.mark.parametrize("tag", ["v9.9.9", "v0.1.0-rc1"])
def test_release_tag_must_match_stable_project_version(release, tag):
    with pytest.raises(ValueError, match="tag must match"):
        release[2](tag, "example/project")
