"""Build selectable targets from Kitty windows or published workspaces."""

import fcntl
import json
import math
import os
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path


def clean(value):
    """Keep metadata from introducing terminal controls or extra records."""
    return "".join(
        char for char in " · ".join(str(value or "").splitlines()) if char.isprintable()
    )


def source_health(source):
    if source.get("error"):
        return "collector failed: " + clean(source["error"])
    if source.get("observed_at") is None:
        return "awaiting first observation"
    if source.get("stale"):
        return "observation expired"
    return "healthy"


STATES = {"idle", "working", "done", "blocked", "error"}


def workspace_status(metadata):
    status = metadata.get("status")
    marker = clean(metadata.get("status_character")) or "—"
    return f"{marker} {status or 'unknown'}"


def timestamp(value):
    if isinstance(value, (int, float)):
        try:
            return datetime.fromtimestamp(value, UTC).isoformat(timespec="seconds")
        except (ValueError, OverflowError, OSError):
            pass
    return clean(value)


@dataclass(frozen=True)
class Candidate:
    kind: str
    id: int
    name: str
    metadata: dict = field(default_factory=dict)
    panes: list[dict] = field(default_factory=list)
    collector: dict = field(default_factory=dict)

    @property
    def key(self):
        return f"{self.kind}:{self.id}"

    @property
    def focus_command(self):
        return [f"focus-{self.kind}", "--match", f"id:{self.id}"]

    def columns(self):
        if self.kind == "window":
            return (clean(self.name),)
        session = self.metadata.get("representative_session") or {}
        project = clean(self.metadata.get("project")) or "—"
        title = clean(
            self.metadata.get("manual_name")
            or session.get("title")
            or self.metadata.get("worktree")
            or self.name
        )
        agent = clean(session.get("agent")) or "—"
        status = workspace_status(self.metadata)
        return title, project, agent, status

    def row(self):
        return self.key + "\t" + "  ".join(self.columns())

    def debug(self):
        """Preserve every field of the selected provider entry as safe JSON."""
        return json.dumps(self.metadata, indent=2, ensure_ascii=True) + "\n"

    def preview(self):
        lines = [clean(self.name), "", f"Target: {self.kind} {self.id}"]
        for label, key in (
            ("Project", "project"),
            ("Worktree", "worktree"),
            ("Branch", "branch"),
            ("Directory", "cwd"),
            ("Repository", "repository_root"),
            ("Worktree root", "worktree_root"),
        ):
            if self.metadata.get(key):
                lines.append(f"{label}: {clean(self.metadata[key])}")
        if self.kind == "tab":
            lines.extend(
                [
                    f"Status: {workspace_status(self.metadata)}",
                    f"Active tab: {bool(self.metadata.get('is_active'))}",
                    f"Focused: {bool(self.metadata.get('is_focused'))}",
                ]
            )
        if self.collector:
            lines.extend(["", "Collector health: " + source_health(self.collector)])
            observed = self.collector.get("observed_at")
            lines.append(
                "  Last observation: "
                + (timestamp(observed) if observed is not None else "never")
            )
        sessions = self.metadata.get("sessions") or []
        if sessions:
            lines.extend(["", f"Sessions ({len(sessions)}):"])
            for session in sessions:
                lines.append(
                    "  "
                    + " · ".join(
                        clean(session.get(key)) or "—"
                        for key in ("agent", "title", "status")
                    )
                )
                if session.get("cwd"):
                    lines.append("    Directory: " + clean(session["cwd"]))
                lines.append(
                    f"    Pane: {session.get('window_id')}  Process: {session.get('pid')}"
                )
        lines.extend(["", f"Panes ({len(self.panes)}):"])
        for pane in self.panes:
            marker = (
                " *" if pane.get("id") == self.metadata.get("active_window_id") else ""
            )
            lines.append(f"  {pane['id']}{marker}: {clean(pane.get('title'))}")
            if pane.get("cwd"):
                lines.append(f"    {clean(pane['cwd'])}")
        return "\n".join(lines) + "\n"


def format_table(candidates, measure=len):
    """Size columns across the whole snapshot, using terminal cell widths."""
    if not candidates:
        return "", ""
    headers = (
        ("SESSION / BRANCH", "PROJECT", "AGENT", "STATUS")
        if candidates[0].kind == "tab"
        else ()
    )
    rows = [candidate.columns() for candidate in candidates]
    widths = [
        max(measure(row[index]) for row in rows + ([headers] if headers else []))
        for index in range(len(rows[0]))
    ]

    def format_cells(cells):
        return "  ".join(
            value + " " * (width - measure(value))
            for value, width in zip(cells, widths, strict=True)
        ).rstrip()

    entries = "\n".join(
        candidate.key + "\t" + format_cells(cells)
        for candidate, cells in zip(candidates, rows, strict=True)
    )
    return entries, format_cells(headers) if headers else ""


@contextmanager
def picker_lock(state, self_id):
    """Allow one picker per tab, releasing the lock even if fzf is interrupted."""
    tab_id = next(
        tab["id"]
        for os_window in state
        for tab in os_window["tabs"]
        if any(window["id"] == self_id for window in tab["windows"])
    )
    cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
    directory = cache / "kitty-workspace-picker"
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{os.environ['KITTY_PID']}-{tab_id}.lock"
    # Keep the file in place: unlinking it can let contenders lock different inodes.
    with path.open("a") as lock:
        try:
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(lock, fcntl.LOCK_UN)


@dataclass(frozen=True)
class PublishedWorkspaces:
    workspaces: list[dict]
    collector: dict = field(default_factory=dict)


def optional_fields_valid(value, fields):
    """Validate fields we interpret; preserve unknown fields for debug output."""
    return all(
        value.get(key) is None or check(value[key]) for key, check in fields.items()
    )


def string(value):
    return isinstance(value, str)


def integer(value):
    # bool is an int subclass, but is not a valid identifier or count.
    return type(value) is int


def boolean(value):
    return type(value) is bool


def session_list(value):
    return isinstance(value, list) and all(session_valid(item) for item in value)


def number(value):
    if integer(value):
        return True
    return type(value) is float and math.isfinite(value)


def status_valid(value):
    return isinstance(value, str) and value in STATES


def session_valid(value):
    return isinstance(value, dict) and optional_fields_valid(
        value,
        {
            **dict.fromkeys(("agent", "title", "cwd", "status_character"), string),
            "status": status_valid,
            "window_id": integer,
            "pid": integer,
        },
    )


def workspace_valid(item):
    return (
        isinstance(item, dict)
        and type(item.get("id")) is int
        and isinstance(item.get("name"), str)
        and isinstance(item.get("window_ids"), list)
        and all(type(value) is int for value in item["window_ids"])
        and optional_fields_valid(
            item,
            {
                "sessions": session_list,
                "representative_session": session_valid,
                **dict.fromkeys(
                    (
                        "project",
                        "manual_name",
                        "worktree",
                        "status_character",
                        "cwd",
                        "branch",
                        "repository_root",
                        "worktree_root",
                    ),
                    string,
                ),
                "status": status_valid,
                **dict.fromkeys(
                    ("is_active", "is_focused"),
                    boolean,
                ),
                **dict.fromkeys(
                    ("last_visited_order", "active_window_id", "os_window_id"),
                    integer,
                ),
            },
        )
    )


def collector_valid(value):
    return isinstance(value, dict) and optional_fields_valid(
        value, {"observed_at": number, "error": string, "stale": boolean}
    )


def published_workspaces(config_dir, remote_control):
    """Read the optional provider endpoint; absence/failure means window mode."""
    endpoint = Path(config_dir) / "kitty_workspaces/kitten.py"
    if not endpoint.is_file():
        return None
    try:
        result = remote_control(
            ["kitten", str(endpoint)], capture_output=True, text=True, check=False
        )
    except (OSError, TimeoutError, subprocess.TimeoutExpired):
        return None
    if result.returncode:
        return None
    try:
        data = json.loads(result.stdout)
    except (ValueError, TypeError):
        return None
    if (
        not isinstance(data, dict)
        or type(data.get("version")) is not int
        or data["version"] != 1
    ):
        return None
    items = data.get("workspaces")
    if not isinstance(items, list):
        return None
    collector = data.get("collector", {})
    if not all(workspace_valid(item) for item in items) or not collector_valid(
        collector
    ):
        return None
    return PublishedWorkspaces(items, collector)


def scoped_state(state, self_id):
    """Locate the caller by pane ID; never fall back to another OS window."""
    return [
        os_window
        for os_window in state
        if any(
            window["id"] == self_id
            for tab in os_window["tabs"]
            for window in tab["windows"]
        )
    ]


def movement_candidates(state, self_id, workspaces, mode):
    state = scoped_state(state, self_id)
    if not state:
        return []
    current = next(
        tab
        for tab in state[0]["tabs"]
        if any(pane["id"] == self_id for pane in tab["windows"])
    )
    metadata = {
        item.id: item
        for item in candidates(state, self_id, workspaces)
        if item.kind == "tab"
    }
    result = []
    for tab in state[0]["tabs"]:
        if tab["id"] == current["id"]:
            continue
        workspace = metadata.get(tab["id"])
        name = workspace.name if workspace else tab.get("title", str(tab["id"]))
        if mode == "send":
            result.append(
                workspace
                or Candidate(
                    "tab", tab["id"], name, {"manual_name": name}, tab["windows"]
                )
            )
        else:
            for pane in tab["windows"]:
                if pane.get("is_self") or pane.get("is_overlay"):
                    continue
                sessions = workspace.metadata.get("sessions", []) if workspace else []
                session = next(
                    (item for item in sessions if item.get("window_id") == pane["id"]),
                    {},
                )
                label = " · ".join(
                    filter(
                        None,
                        [
                            name,
                            pane.get("title"),
                            session.get("agent"),
                            session.get("status"),
                        ],
                    )
                )
                result.append(Candidate("window", pane["id"], label, pane, [pane]))
    return result


def candidates(state, self_id, workspaces=None):
    state = scoped_state(state, self_id)
    tab_ids = {tab["id"] for os_window in state for tab in os_window["tabs"]}
    collector = {}
    if isinstance(workspaces, PublishedWorkspaces):
        collector = workspaces.collector
        workspaces = workspaces.workspaces
    if workspaces is not None:
        workspaces = [item for item in workspaces if item["id"] in tab_ids]
    excluded = {
        window["id"]
        for os_window in state
        for tab in os_window["tabs"]
        for window in tab["windows"]
        if window["id"] == self_id or window.get("is_self", False)
    }
    if workspaces is not None:
        current_tab = next(
            (
                tab["id"]
                for os_window in state
                for tab in os_window["tabs"]
                if any(window["id"] == self_id for window in tab["windows"])
            ),
            None,
        )

        def recency_key(item):
            order = item.get("last_visited_order")
            return (
                item["id"] == current_tab,
                -order if type(order) is int else 0,
            )

        # Stable sorting keeps unvisited tabs in provider order.
        ordered = (
            sorted(workspaces, key=recency_key)
            if any(type(item.get("last_visited_order")) is int for item in workspaces)
            else workspaces
        )
        for item in ordered:
            panes = [
                window
                for os_window in state
                for tab in os_window["tabs"]
                for window in tab["windows"]
                if window["id"] in item["window_ids"]
            ]
            yield Candidate("tab", item["id"], item["name"], item, panes, collector)
        return
    for os_window in state:
        for tab in os_window["tabs"]:
            for window in tab["windows"]:
                if window["id"] not in excluded:
                    yield Candidate(
                        "window", window["id"], window["title"], window, [window]
                    )
