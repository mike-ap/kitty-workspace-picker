"""Exercise selection and Kitty's overlay completion callback."""

import runpy
import shlex
import subprocess
import sys
from pathlib import Path
from types import ModuleType, SimpleNamespace

import pytest

from kitty_workspace_picker import picker


@pytest.fixture
def kitten(monkeypatch, tmp_path):
    handler = ModuleType("kittens.tui.handler")
    handler.kitten_ui = lambda **kwargs: lambda func: func
    handler.result_handler = lambda **kwargs: lambda func: func
    fast_data_types = ModuleType("kitty.fast_data_types")
    fast_data_types.wcswidth = len
    fast_data_types.add_timer = lambda callback, delay, repeat: callback(1)
    monkeypatch.setitem(sys.modules, "kittens.tui.handler", handler)
    monkeypatch.setitem(sys.modules, "kitty.fast_data_types", fast_data_types)
    monkeypatch.setenv("KITTY_CONFIG_DIRECTORY", str(tmp_path))
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return runpy.run_path(
        str(
            Path(__file__).resolve().parents[1] / "src/kitty_workspace_picker/kitten.py"
        )
    )


@pytest.mark.parametrize("kind", ["window", "tab"])
def test_enter_returns_focus_command_for_after_overlay_closes(
    kitten, monkeypatch, kind
):
    candidate = picker.Candidate(kind, 20, "Editor")
    monkeypatch.setattr(picker, "published_workspaces", lambda *args: None)
    monkeypatch.setattr(picker, "candidates", lambda *args: iter([candidate]))

    def run(command, **kwargs):
        assert "--bind=enter:accept" in command
        # Static headers must bypass --with-nth, which strips the key column.
        header = next(arg for arg in command if arg.startswith("--header="))
        for legend in (
            "Enter: focus",
            "Ctrl+/: details",
            "F2: debug",
        ):
            assert legend in header
        assert "Alt+" not in header
        assert header.endswith(picker.format_table([candidate])[1])
        assert "--header-lines=3" not in command
        assert kwargs["input"] == picker.format_table([candidate])[0] + "\n"
        return SimpleNamespace(returncode=0, stdout=candidate.row() + "\n")

    def remote(*args, **kwargs):
        pytest.fail("Focus must wait until Kitty closes the overlay")

    monkeypatch.setattr(kitten["subprocess"], "run", run)
    kitten["main"].remote_control = remote
    command = kitten["run_picker"](picker, [], 10)
    assert command == candidate.focus_command

    calls = []
    target_window = object()
    boss = SimpleNamespace(
        window_id_map={10: target_window},
        call_remote_control=lambda *args: calls.append(args),
    )
    kitten["handle_result"]([], command, 10, boss)
    assert calls == [(target_window, tuple(candidate.focus_command))]


@pytest.mark.parametrize(
    ("label", "expected"),
    [
        (
            "",
            "show-preview+change-preview-label(Debug · Alt+J/K: scroll · Alt+F/B: page)",
        ),
        (
            "Details · Alt+J/K: scroll · Alt+F/B: page",
            "show-preview+change-preview-label(Debug · Alt+J/K: scroll · Alt+F/B: page)",
        ),
        (
            "Debug · Alt+J/K: scroll · Alt+F/B: page",
            "hide-preview+change-preview-label()",
        ),
    ],
)
def test_debug_preview_toggle(kitten, monkeypatch, label, expected):
    shell_run = subprocess.run
    monkeypatch.setenv("SHELL", "/usr/local/bin/fish")
    monkeypatch.setattr(picker, "published_workspaces", lambda *args: None)
    monkeypatch.setattr(
        picker, "candidates", lambda *args: iter([picker.Candidate("window", 20, "x")])
    )

    def run(command, **kwargs):
        binding = next(arg for arg in command if arg.startswith("--bind=f2:"))
        transform = binding.split("+transform:", 1)[1]
        shell = next(arg for arg in command if arg.startswith("--with-shell="))
        assert shell == "--with-shell=sh -c"
        result = shell_run(
            [*shlex.split(shell.split("=", 1)[1]), transform],
            env={**kwargs["env"], "FZF_PREVIEW_LABEL": label},
            capture_output=True,
            text=True,
            check=True,
        )
        assert result.stdout == expected
        details = next(arg for arg in command if arg.startswith("--bind=ctrl-/:"))
        assert (
            "+change-preview-label(Details · Alt+J/K: scroll · Alt+F/B: page)+toggle-preview"
            in details
        )
        return SimpleNamespace(returncode=130, stdout="")

    monkeypatch.setattr(kitten["subprocess"], "run", run)
    assert kitten["run_picker"](picker, [], 10) is None


@pytest.mark.parametrize("returncode", [1, 130])
def test_cancel_returns_no_focus_command(kitten, monkeypatch, returncode):
    monkeypatch.setattr(picker, "published_workspaces", lambda *args: None)
    monkeypatch.setattr(
        picker, "candidates", lambda *args: iter([picker.Candidate("window", 20, "x")])
    )
    monkeypatch.setattr(
        kitten["subprocess"],
        "run",
        lambda *args, **kwargs: SimpleNamespace(returncode=returncode, stdout=""),
    )
    kitten["main"].remote_control = lambda *args: None
    assert kitten["run_picker"](picker, [], 10) is None


def test_picker_reads_one_snapshot_without_polling_or_reload(kitten, monkeypatch):
    import shlex

    candidate = picker.Candidate("window", 20, "Editor")
    reads = []
    monkeypatch.setattr(
        picker, "published_workspaces", lambda *args: reads.append(args)
    )
    monkeypatch.setattr(picker, "candidates", lambda *args: iter([candidate]))
    kitten["main"].remote_control = lambda *args, **kwargs: pytest.fail(
        "Picker must not poll Kitty"
    )

    def run(command, **kwargs):
        assert command[0] == "fzf"
        assert not any("reload" in arg or "listen=" in arg for arg in command)
        assert candidate.row() in kwargs["input"]
        preview = next(arg for arg in command if arg.startswith("--preview=cat -- "))
        directory = Path(shlex.split(preview.split("cat -- ", 1)[1])[0]).parent
        assert (directory / candidate.key).read_text() == candidate.preview()
        assert (directory / (candidate.key + ".json")).read_text() == candidate.debug()
        return SimpleNamespace(returncode=0, stdout=candidate.row() + "\n")

    monkeypatch.setattr(kitten["subprocess"], "run", run)
    assert kitten["run_picker"](picker, [], 10) == candidate.focus_command
    assert len(reads) == 1


@pytest.mark.parametrize("mode", ["merge", "send"])
def test_move_runs_after_overlay_closes_and_uses_captured_ids(kitten, mode):
    calls = []
    source_tab = SimpleNamespace(id=1, os_window_id=100)
    source = SimpleNamespace(id=11, tabref=lambda: source_tab)

    class Tab(list):
        def __init__(self, identity, panes, os_window=100):
            super().__init__(SimpleNamespace(id=identity) for identity in panes)
            self.id = identity
            self.os_window_id = os_window

    boss = SimpleNamespace(
        window_id_map={11: source},
        all_tabs=[Tab(1, [11]), Tab(2, [20]), Tab(3, [30], 200)],
        call_remote_control=lambda source, args: calls.append(args),
        set_active_window=lambda *args, **kwargs: None,
    )
    result = {
        "mode": mode,
        "os_window_id": 100,
        "tab_id": 1,
        "selected_id": 20 if mode == "merge" else 2,
    }
    kitten["handle_result"]([], result, 11, boss)
    assert calls[-1] == (
        "detach-window",
        "--match",
        "id:20" if mode == "merge" else "id:11",
        "--target-tab",
        "id:1" if mode == "merge" else "id:2",
    )
    calls.clear()
    result["selected_id"] = 30 if mode == "merge" else 3
    kitten["handle_result"]([], result, 11, boss)
    assert calls == []
    kitten["handle_result"]([], None, 11, boss)
    assert calls == []


@pytest.mark.parametrize("returncode", [0, 1])
def test_send_new_tab_uses_query_and_native_creation(kitten, monkeypatch, returncode):
    state = [{"id": 100, "tabs": [{"id": 1, "windows": [{"id": 10}]}]}]
    monkeypatch.setattr(picker, "published_workspaces", lambda *args: None)
    monkeypatch.setattr(
        kitten["subprocess"],
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=returncode, stdout="New workspace\nctrl-n\n"
        ),
    )
    assert kitten["run_picker"](picker, state, 10, "send") == {
        "mode": "send",
        "os_window_id": 100,
        "tab_id": 1,
        "name": "New workspace",
    }


def test_remote_control_has_bounded_timeout(kitten):
    calls = []
    kitten["main"].remote_control = lambda *args, **kwargs: calls.append((args, kwargs))
    kitten["remote_control"](["ls"], check=True)
    assert calls == [((["ls"],), {"timeout": 2, "check": True})]


@pytest.mark.parametrize("name", ["", "bad\x1bname"])
def test_send_rejects_empty_or_control_character_names(kitten, monkeypatch, name):
    state = [{"id": 100, "tabs": [{"id": 1, "windows": [{"id": 10}]}]}]
    monkeypatch.setattr(picker, "published_workspaces", lambda *args: None)
    monkeypatch.setattr(
        kitten["subprocess"],
        "run",
        lambda *args, **kwargs: SimpleNamespace(
            returncode=0, stdout=name + "\nctrl-n\n"
        ),
    )
    assert kitten["run_picker"](picker, state, 10, "send") is None


def test_result_ignores_vanished_source(kitten):
    boss = SimpleNamespace(window_id_map={})
    kitten["apply_result"](["focus-window", "--match", "id:2"], 1, boss)


def test_result_ignores_source_moved_to_another_tab(kitten):
    source = SimpleNamespace(tabref=lambda: SimpleNamespace(id=9, os_window_id=100))
    boss = SimpleNamespace(window_id_map={1: source})
    kitten["apply_result"]({"mode": "send", "tab_id": 1, "os_window_id": 100}, 1, boss)


@pytest.mark.parametrize("acquired", [False, True])
def test_main_locks_snapshot_before_opening_picker(kitten, monkeypatch, acquired):
    from contextlib import contextmanager

    calls = []

    @contextmanager
    def lock(state, self_id):
        assert state == [] and self_id == 10
        yield acquired

    provider = SimpleNamespace(picker_lock=lock)
    globals_ = kitten["main"].__globals__
    monkeypatch.setitem(globals_, "picker_module", lambda script: provider)
    monkeypatch.setitem(
        globals_, "run_picker", lambda *args: calls.append(args) or "selected"
    )
    monkeypatch.setenv("KITTY_WINDOW_ID", "10")
    kitten["main"].remote_control = lambda *args, **kwargs: SimpleNamespace(stdout="[]")
    result = kitten["main"](["kitten.py"])
    assert result == ("selected" if acquired else None)
    assert len(calls) == int(acquired)
    with pytest.raises(SystemExit, match="Usage:"):
        kitten["main"](["kitten.py", "invalid"])


def test_package_loader_works_without_custom_kitten_file_global(kitten, monkeypatch):
    import sys

    monkeypatch.setitem(
        sys.modules, "kitty_workspace_picker", sys.modules["kitty_workspace_picker"]
    )
    script = Path(picker.__file__).with_name("kitten.py")
    loaded = kitten["picker_module"](script)
    assert loaded.__file__ == picker.__file__
    assert loaded.clean("safe\x1b") == "safe"
