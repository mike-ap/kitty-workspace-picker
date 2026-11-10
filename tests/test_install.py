import subprocess
from pathlib import Path
from shutil import copy2, copytree

INSTALLER = Path(__file__).resolve().parents[1] / "install.sh"


def install(config):
    return subprocess.run(
        ["sh", str(INSTALLER), "--config-dir", str(config)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_install_is_repeatable_and_preserves_kitty_configuration(tmp_path):
    config = tmp_path / "kitty"
    config.mkdir()
    originals = {
        "kitty.conf": "map ctrl+p next_tab\n",
        "custom_kitten.py": "# custom kitten\n",
    }
    for name, content in originals.items():
        (config / name).write_text(content)
    for _ in range(2):
        assert install(config).returncode == 0
        assert all(
            (config / name).read_text() == content
            for name, content in originals.items()
        )
    assert (config / "kitty_workspace_picker/kitten.py").is_file()
    assert (config / "kitty_workspace_picker" / "picker.py").is_file()
    assert {
        path.relative_to(config).as_posix()
        for path in config.rglob("*")
        if path.is_file()
    } == {
        *originals,
        "kitty_workspace_picker/kitten.py",
        "kitty_workspace_picker/__init__.py",
        "kitty_workspace_picker/picker.py",
        "kitty_workspace_picker/.kitty-workspace-picker",
    }


def test_install_does_not_create_kitty_configuration(tmp_path):
    assert install(tmp_path).returncode == 0
    assert not (tmp_path / "kitty.conf").exists()


def test_install_rejects_unowned_picker_before_writing(tmp_path):
    (tmp_path / "kitty_workspace_picker").mkdir()
    (tmp_path / "kitty_workspace_picker/kitten.py").write_text("existing kitten\n")
    assert install(tmp_path).returncode != 0
    assert not (tmp_path / "kitty_workspace_picker/__init__.py").exists()


def test_install_rejects_unowned_package(tmp_path):
    (tmp_path / "kitty_workspace_picker").mkdir()
    assert install(tmp_path).returncode != 0
    assert not (tmp_path / "kitty_workspace_picker/kitten.py").exists()


def test_install_rejects_symlinked_package_member(tmp_path):
    assert install(tmp_path).returncode == 0
    target = tmp_path / "outside.py"
    target.write_text("untouched\n")
    member = tmp_path / "kitty_workspace_picker" / "picker.py"
    member.unlink()
    member.symlink_to(target)
    assert install(tmp_path).returncode != 0
    assert target.read_text() == "untouched\n"


def test_install_updates_owned_picker(tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    copy2(INSTALLER, source / "install.sh")
    copy2(INSTALLER.parent / "pyproject.toml", source / "pyproject.toml")
    copytree(INSTALLER.parent / "src", source / "src")
    config = tmp_path / "kitty"
    command = ["sh", str(source / "install.sh"), "--config-dir", str(config)]
    subprocess.run(command, check=True)
    with (source / "src" / "kitty_workspace_picker/kitten.py").open("a") as stream:
        stream.write("\n# updated\n")
    subprocess.run(command, check=True)
    assert (
        (config / "kitty_workspace_picker/kitten.py")
        .read_text()
        .endswith("# updated\n")
    )
