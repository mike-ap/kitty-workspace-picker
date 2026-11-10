import json
from types import SimpleNamespace

import pytest

from kitty_workspace_picker import picker


@pytest.fixture(autouse=True)
def provider_directory(tmp_path):
    (tmp_path / "kitty_workspaces").mkdir()


@pytest.fixture
def state():
    return [
        {
            "tabs": [
                {
                    "id": 1,
                    "windows": [
                        {"id": 10, "title": "Picker", "is_self": True},
                        {"id": 11, "title": "Current pane"},
                    ],
                },
                {
                    "id": 2,
                    "windows": [
                        {"id": 20, "title": "Editor"},
                        {"id": 21, "title": "Shell\x07\ncommand"},
                    ],
                },
            ]
        }
    ]


def test_window_fallback_lists_panes_and_only_excludes_picker(state):
    items = list(picker.candidates(state, 10))
    assert [item.row() for item in items] == [
        "window:11\tCurrent pane",
        "window:20\tEditor",
        "window:21\tShell · command",
    ]
    assert items[1].focus_command == ["focus-window", "--match", "id:20"]


def test_workspace_metadata_controls_grouping_and_naming(state):
    metadata = [
        {"id": 1, "name": "Current", "window_ids": [10, 11]},
        {"id": 2, "name": "demo\n● Task", "window_ids": [20, 21]},
    ]
    items = list(picker.candidates(state, 10, metadata))
    assert [item.id for item in items] == [1, 2]
    assert items[1].row().startswith("tab:2\t")
    assert "demo · ● Task" in items[1].row()
    assert items[1].focus_command == ["focus-tab", "--match", "id:2"]


def test_missing_provider_does_not_make_remote_request(tmp_path):
    def remote(*args, **kwargs):
        pytest.fail("Provider is absent")

    assert picker.published_workspaces(tmp_path, remote) is None


@pytest.mark.parametrize(
    "payload",
    [
        None,
        {},
        {"version": 1},
        {"version": 1, "workspaces": [{}]},
        {"version": 1, "workspaces": [{"id": "2", "name": "x", "window_ids": []}]},
    ],
)
def test_incompatible_metadata_falls_back(tmp_path, payload):
    (tmp_path / "kitty_workspaces/kitten.py").touch()
    assert (
        picker.published_workspaces(
            tmp_path,
            lambda *a, **kw: SimpleNamespace(returncode=0, stdout=json.dumps(payload)),
        )
        is None
    )


def test_failed_or_malformed_metadata_falls_back(tmp_path):
    (tmp_path / "kitty_workspaces/kitten.py").touch()
    for code, output in [(1, "error"), (0, "invalid JSON")]:
        assert (
            picker.published_workspaces(
                tmp_path,
                lambda *a, code=code, output=output, **kw: SimpleNamespace(
                    returncode=code, stdout=output
                ),
            )
            is None
        )


def test_provider_endpoint_and_empty_snapshot(tmp_path):
    endpoint = tmp_path / "kitty_workspaces/kitten.py"
    endpoint.touch()

    def remote(command, **kwargs):
        assert command == ["kitten", str(endpoint)]
        assert kwargs == {"capture_output": True, "text": True, "check": False}
        return SimpleNamespace(returncode=0, stdout='{"version":1,"workspaces":[]}')

    assert picker.published_workspaces(tmp_path, remote).workspaces == []


def test_picker_lock_blocks_reentry_and_releases_after_exit(
    state, tmp_path, monkeypatch
):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setenv("KITTY_PID", "123")
    with picker.picker_lock(state, 10) as first:
        assert first
        with picker.picker_lock(state, 11) as nested:
            assert not nested
        with picker.picker_lock(state, 20) as other_tab:
            assert other_tab
    with picker.picker_lock(state, 11) as reopened:
        assert reopened


def test_picker_lock_releases_on_error(state, tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path))
    monkeypatch.setenv("KITTY_PID", "123")
    with pytest.raises(RuntimeError), picker.picker_lock(state, 10):
        raise RuntimeError("Picker interrupted")
    with picker.picker_lock(state, 10) as reopened:
        assert reopened


def test_workspace_details_include_all_sessions_and_non_agent_panes(state):
    metadata = [
        {
            "id": 2,
            "name": "demo\nTask",
            "project": "demo",
            "branch": "feature/ui",
            "cwd": "/code/demo",
            "window_ids": [20, 21],
            "active_window_id": 20,
            "is_active": True,
            "is_focused": False,
            "status": "working",
            "representative_session": {
                "agent": "codex",
                "title": "Task",
                "status": "working",
            },
            "sessions": [
                {
                    "agent": "codex",
                    "title": "Task",
                    "status": "working",
                    "window_id": 20,
                    "pid": 123,
                }
            ],
        }
    ]
    (candidate,) = picker.candidates(state, 10, metadata)
    row = candidate.row()
    assert row.startswith("tab:2\tTask")
    assert row.index("Task") < row.index("demo")
    assert all(value in row for value in ("Task", "codex", "working"))
    preview = candidate.preview()
    assert "Branch: feature/ui" in preview
    assert "Directory: /code/demo" in preview
    assert "Process: 123" in preview
    assert "Panes (2):" in preview
    assert "20 *: Editor" in preview
    assert "21: Shell · command" in preview
    assert "\x07" not in preview


def test_columns_fit_widest_value_and_share_header_alignment():
    items = [
        picker.Candidate("tab", 1, "short", {"project": "x", "worktree": "a"}),
        picker.Candidate(
            "tab",
            2,
            "long",
            {
                "project": "a much longer project name",
                "worktree": "a branch longer than the old fixed column width",
            },
        ),
    ]
    entries, header = picker.format_table(items)
    rows = [row.split("\t", 1)[1] for row in entries.splitlines()]
    project_start = (
        max(len("SESSION / BRANCH"), *(len(item.columns()[0]) for item in items)) + 2
    )
    agent_start = project_start + len("a much longer project name") + 2
    assert header.index("PROJECT") == project_start
    assert header.index("AGENT") == agent_start
    for item, row in zip(items, rows, strict=True):
        assert row[project_start:].startswith(item.columns()[1])
        assert row[agent_start:].startswith("—")
    assert entries.splitlines()[0].startswith("tab:1\t")


def test_table_uses_terminal_cell_measurement():
    item = picker.Candidate(
        "tab", 1, "name", {"worktree": "界" * 20, "project": "demo"}
    )

    def measure(text):
        return sum(2 if char == "界" else 1 for char in text)

    entries, header = picker.format_table([item], measure)
    row = entries.split("\t", 1)[1]
    assert measure(row[: row.index("demo")]) == header.index("PROJECT") == 42


def test_picker_uses_aggregate_status_instead_of_representative_status():
    candidate = picker.Candidate(
        "tab",
        1,
        "demo",
        {
            "project": "demo",
            "status": "working",
            "representative_session": {
                "agent": "claude",
                "title": "Free task",
                "status": "idle",
            },
            "sessions": [
                {
                    "agent": "claude",
                    "title": "Free task",
                    "status": "idle",
                    "window_id": 1,
                },
                {
                    "agent": "codex",
                    "title": "Busy task",
                    "status": "working",
                    "window_id": 2,
                },
            ],
        },
    )
    assert candidate.columns() == ("Free task", "demo", "claude", "— working")
    assert "Status: — working" in candidate.preview()
    assert "claude · Free task · idle" in candidate.preview()
    assert "codex · Busy task · working" in candidate.preview()


def test_debug_preserves_complete_workspace_entry_and_escapes_controls():
    metadata = {
        "id": 2,
        "name": "demo\nTask\x1b[31m",
        "sessions": [{"model": "example", "stale": False, "attention": None}],
        "future_field": {"nested": [1, True, None]},
    }
    candidate = picker.Candidate("tab", 2, metadata["name"], metadata)
    debug = candidate.debug()
    assert json.loads(debug) == metadata
    assert "\x1b" not in debug
    assert '\n  "sessions": [' in debug


def test_single_current_workspace_remains_selectable(state):
    metadata = [{"id": 1, "name": "Current", "window_ids": [10, 11]}]
    (candidate,) = picker.candidates(state, 10, metadata)
    assert candidate.key == "tab:1"


def test_workspace_recency_puts_current_last_and_keeps_unvisited_order(state):
    state[0]["tabs"].extend({"id": identity, "windows": []} for identity in (3, 4, 5))
    metadata = [
        {"id": 1, "name": "Current", "window_ids": [10, 11], "last_visited_order": 8},
        {"id": 3, "name": "Unvisited A", "window_ids": []},
        {"id": 2, "name": "Recent", "window_ids": [20], "last_visited_order": 7},
        {"id": 4, "name": "Unvisited B", "window_ids": [], "last_visited_order": None},
        {"id": 5, "name": "Older", "window_ids": [], "last_visited_order": 2},
    ]
    assert [item.id for item in picker.candidates(state, 10, metadata)] == [
        2,
        5,
        3,
        4,
        1,
    ]
    # Sorting does not mutate provider metadata, and survives overlay focus flags.
    assert metadata[0]["id"] == 1


def test_optional_nulls_and_future_fields_remain_compatible(state, tmp_path):
    (tmp_path / "kitty_workspaces/kitten.py").touch()
    item = {
        "id": 2,
        "name": "Demo",
        "window_ids": [20],
        "sessions": None,
        "representative_session": None,
        "attention": None,
        "project": None,
        "future": {"nested": [1, None]},
    }
    result = picker.published_workspaces(
        tmp_path,
        lambda *a, **kw: SimpleNamespace(
            returncode=0, stdout=json.dumps({"version": 1, "workspaces": [item]})
        ),
    )
    (candidate,) = picker.candidates(state, 10, result)
    assert json.loads(candidate.debug()) == item
    assert candidate.preview()
    assert picker.format_table([candidate])[0]


def test_provider_timeout_falls_back(tmp_path):
    import subprocess

    (tmp_path / "kitty_workspaces/kitten.py").touch()

    def remote(*args, **kwargs):
        raise subprocess.TimeoutExpired("kitten", 2)

    assert picker.published_workspaces(tmp_path, remote) is None


@pytest.mark.parametrize(
    "status, marker",
    [
        ("idle", "○"),
        ("working", "●"),
        ("done", "✓"),
        ("blocked", "?"),
        ("error", "!"),
        (None, "—"),
    ],
)
def test_version_one_native_states_in_rows_and_preview(tmp_path, state, status, marker):
    (tmp_path / "kitty_workspaces/kitten.py").touch()
    session = {
        "agent": "codex",
        "window_id": 20,
        "pid": 123,
        "title": "Task",
        "status": status,
        "cwd": "/demo",
        "status_character": marker,
    }
    item = {
        "id": 2,
        "name": "Demo",
        "window_ids": [20],
        "sessions": [session],
        "representative_session": session,
        "status": status,
        "status_character": marker,
    }
    data = {
        "version": 1,
        "collector": {"observed_at": 120, "error": None, "stale": False},
        "workspaces": [item],
    }
    result = picker.published_workspaces(
        tmp_path,
        lambda *a, **kw: SimpleNamespace(returncode=0, stdout=json.dumps(data)),
    )
    (candidate,) = picker.candidates(state, 10, result)
    assert candidate.columns()[3] == f"{marker} {status or 'unknown'}"
    preview = candidate.preview()
    assert "Process: 123" in preview
    assert "Collector health: healthy" in preview
    assert not any(
        label in preview
        for label in ("Last turn:", "Match:", "Native lifecycle:", "unread completion")
    )


@pytest.mark.parametrize(
    "extra",
    [
        {"status": "busy"},
        {"status": []},
        {"sessions": [None]},
        {"sessions": [{"pid": True}]},
        {"sessions": [{"status": "future"}]},
        {"last_visited_order": True},
        {"project": {}},
    ],
)
def test_version_one_rejects_malformed_interpreted_fields(tmp_path, extra):
    (tmp_path / "kitty_workspaces/kitten.py").touch()
    data = {
        "version": 1,
        "workspaces": [{"id": 2, "name": "Demo", "window_ids": [20], **extra}],
    }
    assert (
        picker.published_workspaces(
            tmp_path,
            lambda *a, **kw: SimpleNamespace(returncode=0, stdout=json.dumps(data)),
        )
        is None
    )


def test_unsupported_version_is_rejected(tmp_path):
    (tmp_path / "kitty_workspaces/kitten.py").touch()
    data = {"version": 2, "workspaces": []}
    assert (
        picker.published_workspaces(
            tmp_path,
            lambda *a, **kw: SimpleNamespace(returncode=0, stdout=json.dumps(data)),
        )
        is None
    )


def test_scope_uses_actual_tab_membership_even_with_stale_provider(state):
    state.append(
        {"id": 99, "tabs": [{"id": 9, "windows": [{"id": 90, "title": "Elsewhere"}]}]}
    )
    metadata = [
        {"id": identity, "name": str(identity), "window_ids": []}
        for identity in (1, 2, 9)
    ]
    assert [item.id for item in picker.candidates(state, 10, metadata)] == [1, 2]
    assert 90 not in [item.id for item in picker.candidates(state, 10)]
    assert list(picker.candidates(state, 999, metadata)) == []
    assert [
        item.id for item in picker.movement_candidates(state, 10, None, "merge")
    ] == [20, 21]
    assert [
        item.id for item in picker.movement_candidates(state, 10, None, "send")
    ] == [2]
