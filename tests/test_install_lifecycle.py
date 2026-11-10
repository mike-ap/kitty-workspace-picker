"""Verify upgrades and removal against a disposable installed copy."""

import re
import shutil
import subprocess
import tomllib
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
PROJECT = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
PACKAGE = re.sub(r"[-_.]+", "_", PROJECT["name"])


@pytest.fixture
def installation(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    for name in ("install.sh", "pyproject.toml"):
        shutil.copy2(ROOT / name, source / name)
    shutil.copytree(
        ROOT / "src", source / "src", ignore=shutil.ignore_patterns("__pycache__")
    )
    config = tmp_path / "config"
    command = ["sh", str(source / "install.sh"), "--config-dir", str(config)]
    subprocess.run(command, check=True, capture_output=True)
    return source, config, command


def test_upgrade_records_version_and_removes_obsolete_modules_and_caches(installation):
    source, config, command = installation
    package = config / PACKAGE
    marker = package / ("." + PROJECT["name"])
    marker.write_text(f"Installed by {PROJECT['name']}\n")  # Legacy marker.
    (package / "obsolete.py").write_text("# obsolete\n")
    (package / "notes.txt").write_text("keep me")
    (package / "__pycache__").mkdir()
    (package / "__pycache__/obsolete.cpython-312.pyc").write_bytes(b"old")
    cache = config / "__pycache__"
    cache.mkdir()
    (cache / f"{PACKAGE}.cpython-312.pyc").write_bytes(b"old")
    (cache / "custom.cpython-312.pyc").write_bytes(b"keep")
    metadata = source / "pyproject.toml"
    metadata.write_text(
        metadata.read_text().replace(
            f'version = "{PROJECT["version"]}"', 'version = "0.2.0"'
        )
    )
    subprocess.run(command, check=True, capture_output=True)
    assert marker.read_text().splitlines() == [
        f"Installed by {PROJECT['name']}",
        "version=0.2.0",
    ]
    assert not (package / "obsolete.py").exists()
    assert not (package / "__pycache__").exists()
    assert not (cache / f"{PACKAGE}.cpython-312.pyc").exists()
    assert (cache / "custom.cpython-312.pyc").read_bytes() == b"keep"
    assert (package / "notes.txt").read_text() == "keep me"


@pytest.mark.parametrize("extra_file", [False, True])
def test_uninstall_preserves_configuration_and_extra_files(installation, extra_file):
    _, config, command = installation
    originals = {
        "kitty.conf": "# user config",
        "tab_bar.py": "# user hook",
        "other_kitten.py": "# other kitten",
    }
    for name, content in originals.items():
        (config / name).write_text(content)
    if extra_file:
        (config / PACKAGE / "notes.txt").write_text("keep me")
    subprocess.run([*command, "--uninstall"], check=True, capture_output=True)
    for name, content in originals.items():
        assert (config / name).read_text() == content
    assert not (config / f"{PACKAGE}.py").exists()
    assert not list((config / PACKAGE).glob("*.py"))
    assert (config / PACKAGE / ("." + PROJECT["name"])).is_file()
    if extra_file:
        assert (config / PACKAGE / "notes.txt").read_text() == "keep me"
    else:
        assert (config / PACKAGE).is_dir()  # The ownership record is preserved.
        subprocess.run([*command, "--uninstall"], check=True, capture_output=True)


@pytest.mark.parametrize("shared", [False, True])
@pytest.mark.parametrize("uninstall", [False, True])
def test_symlinked_cache_is_rejected_before_changes(
    installation, tmp_path, shared, uninstall
):
    _, config, command = installation
    outside = tmp_path / "outside"
    outside.mkdir()
    sentinel = outside / "keep.pyc"
    sentinel.write_bytes(b"keep")
    parent = config if shared else config / PACKAGE
    (parent / "__pycache__").symlink_to(outside, target_is_directory=True)
    before = (config / PACKAGE / "kitten.py").read_bytes()
    result = subprocess.run(
        command + (["--uninstall"] if uninstall else []), capture_output=True
    )
    assert result.returncode != 0
    assert sentinel.read_bytes() == b"keep"
    assert (config / PACKAGE / "kitten.py").read_bytes() == before


def test_invalid_ownership_marker_prevents_uninstall(installation):
    _, config, command = installation
    (config / PACKAGE / ("." + PROJECT["name"])).write_text("not installer-owned")
    result = subprocess.run([*command, "--uninstall"], capture_output=True)
    assert result.returncode != 0
    assert (config / PACKAGE / "kitten.py").is_file()


@pytest.mark.parametrize("symlink", [False, True])
def test_upgrade_preserves_existing_configuration(installation, tmp_path, symlink):
    _, config, command = installation
    installed = config / PACKAGE / (PROJECT["name"] + ".conf")
    outside = tmp_path / "custom-config"
    if symlink:
        outside.write_text("# user configuration\n")
        installed.symlink_to(outside)
    else:
        installed.write_text("# user configuration\n")
    subprocess.run(command, check=True, capture_output=True)
    assert installed.is_symlink() == symlink
    assert installed.read_text() == "# user configuration\n"


def test_install_keeps_only_package_and_tab_bar_example_at_root(installation):
    _, config, _ = installation
    expected = {PACKAGE}
    assert {path.name for path in config.iterdir()} == expected
    assert (config / PACKAGE / "kitten.py").is_file()
    assert not (config / PACKAGE / (PROJECT["name"] + ".conf")).exists()


def test_reinstall_preserves_root_configuration_and_removes_owned_entrypoint(
    installation,
):
    _, config, command = installation
    old_config = config / (PROJECT["name"] + ".conf")
    old_config.write_text("# custom configuration\n")
    entrypoint = config / f"{PACKAGE}.py"
    entrypoint.write_text("# previously installed entry point\n")
    subprocess.run(command, check=True, capture_output=True)
    assert old_config.read_text() == "# custom configuration\n"
    assert not entrypoint.exists()


def test_reinstall_after_uninstall_preserves_package_configuration(installation):
    _, config, command = installation
    example = config / PACKAGE / (PROJECT["name"] + ".conf")
    example.write_text("# edited configuration\n")
    subprocess.run([*command, "--uninstall"], check=True, capture_output=True)
    subprocess.run(command, check=True, capture_output=True)
    assert example.read_text() == "# edited configuration\n"
    assert (config / PACKAGE / "kitten.py").is_file()


@pytest.mark.parametrize("at_root", [False, True])
def test_upgrade_preserves_legacy_configuration_example(installation, at_root):
    _, config, command = installation
    previous = (config if at_root else config / PACKAGE) / (
        PROJECT["name"] + ".conf.example"
    )
    previous.write_text("# edited legacy configuration\n")
    subprocess.run(command, check=True, capture_output=True)
    assert previous.read_text() == "# edited legacy configuration\n"
