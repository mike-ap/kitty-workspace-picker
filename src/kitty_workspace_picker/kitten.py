"""Fzf window picker with optional published workspace metadata."""

import importlib.util
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from tempfile import TemporaryDirectory

from kittens.tui.handler import kitten_ui, result_handler
from kitty.fast_data_types import add_timer, wcswidth

REMOTE_TIMEOUT = 2


def remote_control(command, **kwargs):
    return main.remote_control(command, timeout=REMOTE_TIMEOUT, **kwargs)


def picker_module(script):
    path = Path(script).with_name("__init__.py")
    spec = importlib.util.spec_from_file_location("kitty_workspace_picker", path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module.picker


# Kitty 0.49.2 rejects the password-restricted channel in socket-only mode.
# Use the dedicated channel explicitly granted to this kitten instead.
@kitten_ui(allow_remote_control=True)
def main(args):
    # Kitty's custom-kitten loader does not define __file__.
    script = Path(os.environ["KITTY_CONFIG_DIRECTORY"]) / args[0]
    picker = picker_module(script)
    mode = args[1] if len(args) > 1 else "focus"
    if mode not in {"focus", "merge", "send"}:
        raise SystemExit("Usage: kitten.py [focus|merge|send]")
    state = json.loads(remote_control(["ls"], check=True, capture_output=True).stdout)
    self_id = int(os.environ.get("KITTY_WINDOW_ID", "0"))
    with picker.picker_lock(state, self_id) as acquired:
        if acquired:
            return run_picker(picker, state, self_id, mode)
    return None


def run_picker(picker, state, self_id, mode="focus"):
    workspaces = picker.published_workspaces(
        os.environ["KITTY_CONFIG_DIRECTORY"], remote_control
    )
    candidates = (
        list(picker.candidates(state, self_id, workspaces))
        if mode == "focus"
        else picker.movement_candidates(state, self_id, workspaces, mode)
    )
    origin = None
    if mode != "focus":
        scoped = picker.scoped_state(state, self_id)
        if not scoped:
            return None
        tab = next(
            tab
            for tab in scoped[0]["tabs"]
            if any(pane["id"] == self_id for pane in tab["windows"])
        )
        origin = {"os_window_id": scoped[0]["id"], "tab_id": tab["id"]}
    entries, _ = picker.format_table(candidates, wcswidth)
    if not entries and mode != "send":
        return None
    latest = {candidate.key: candidate for candidate in candidates}
    with TemporaryDirectory(prefix="kitty-workspace-picker-") as directory:
        for candidate in candidates:
            for suffix, content in (
                ("", candidate.preview()),
                (".json", candidate.debug()),
            ):
                (Path(directory) / (candidate.key + suffix)).write_text(content)
        entries, header = picker.format_table(candidates, wcswidth)
        action = "focus" if mode == "focus" else "move"
        help_line = f"Enter: {action} · Esc: close · Ctrl+/: details · F2: debug"
        if mode == "send":
            help_line += " · Ctrl+N: create tab named by query"
        rows = entries + "\n"
        env = os.environ.copy()
        env.pop("FZF_DEFAULT_OPTS_FILE", None)
        env.pop("FZF_API_KEY", None)
        env["FZF_DEFAULT_OPTS"] = env.get("KITTY_WORKSPACE_PICKER_FZF_OPTS", "")
        selected = subprocess.run(
            [
                "fzf",
                # Preview transforms use POSIX syntax, regardless of login shell.
                "--with-shell=sh -c",
                "--no-multi",
                *(["--print-query", "--expect=ctrl-n"] if mode == "send" else []),
                "--tiebreak=index",
                "--header=" + help_line + "\n\n" + header,
                "--bind=enter:accept",
                "--layout=reverse",
                "--border=rounded",
                "--with-nth=2..",
                "--delimiter=\t",
                "--prompt=Bring pane here > "
                if mode == "merge"
                else "--prompt=Send pane to > "
                if mode == "send"
                else "--prompt=Workspace > "
                if workspaces is not None
                else "--prompt=Window > ",
                "--preview=cat -- " + shlex.quote(directory) + "/{1}",
                "--preview-window=right,45%,wrap,hidden,<45(down,45%,wrap,hidden)",
                "--bind=ctrl-/:change-preview(cat -- "
                + shlex.quote(directory)
                + "/{1})+change-preview-label(Details · Alt+J/K: scroll · Alt+F/B: page)+toggle-preview",
                "--bind=alt-j:preview-down,alt-k:preview-up",
                "--bind=alt-f:preview-page-down,alt-b:preview-page-up",
                "--bind=f2:change-preview(cat -- "
                + shlex.quote(directory)
                + "/{1}.json)+transform:"
                'if [ "$FZF_PREVIEW_LABEL" = "Debug · Alt+J/K: scroll · Alt+F/B: page" ]; then '
                "printf '%s' 'hide-preview+change-preview-label()'; "
                "else printf '%s' 'show-preview+change-preview-label(Debug · Alt+J/K: scroll · Alt+F/B: page)'; fi",
            ],
            input=rows,
            text=True,
            capture_output=True,
            check=False,
            env=env,
        )
    if selected.returncode == 0 or (mode == "send" and selected.returncode == 1):
        output = selected.stdout
        if mode == "send":
            query, _, output = output.partition("\n")
            keypress, _, output = output.partition("\n")
            if keypress == "ctrl-n":
                name = query.strip()
                if name and picker.clean(name) == name:
                    return {"mode": mode, **origin, "name": name}
                return None
        key = output.partition("\t")[0]
        candidate = latest.get(key)
        if candidate is not None:
            if mode == "focus":
                return candidate.focus_command
            return {"mode": mode, **origin, "selected_id": candidate.id}
    return None


@result_handler()
def handle_result(args, command, target_window_id, boss):
    # Kitty runs this after the picker overlay closes, so focus cannot leave a
    # still-open picker behind or be restored over the selected target on exit.
    if not command:
        return
    # Kitty invokes this during overlay removal. Defer matching until its pane
    # groups no longer contain the dead overlay ID (Kitty 0.50).
    add_timer(
        lambda timer_id: apply_result(command, target_window_id, boss), 0.01, False
    )


def apply_result(command, target_window_id, boss):
    source = boss.window_id_map.get(target_window_id)
    if source is None:
        return
    if isinstance(command, list):
        boss.call_remote_control(source, tuple(command))
        return
    source_tab = source.tabref()
    if (
        source_tab is None
        or source_tab.id != command["tab_id"]
        or source_tab.os_window_id != command["os_window_id"]
    ):
        return
    tabs = {
        tab.id: tab
        for tab in boss.all_tabs
        if tab.os_window_id == command["os_window_id"]
    }
    if command["mode"] == "merge":
        pane_id = command["selected_id"]
        if not any(
            pane.id == pane_id
            for tab in tabs.values()
            if tab.id != source_tab.id
            for pane in tab
        ):
            return
        destination = source_tab.id
    else:
        pane_id = source.id
        destination = command.get("selected_id")
        if destination is not None and destination not in tabs:
            return
    # Restore the captured source before native operations that create a tab.
    boss.set_active_window(source.id, switch_os_window_if_needed=True)
    if destination is None:
        move = (
            "detach-window",
            "--match",
            f"id:{pane_id}",
            "--target-tab=@title",
            "--tab-title",
            command["name"],
            "--create-if-missing",
        )
    else:
        boss.call_remote_control(
            source, ("goto-layout", "--match", f"id:{destination}", "splits")
        )
        move = (
            "detach-window",
            "--match",
            f"id:{pane_id}",
            "--target-tab",
            f"id:{destination}",
        )
    boss.call_remote_control(source, move)
