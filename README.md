# Kitty Workspace Picker

An fzf picker for Kitty windows, with [Kitty
Workspaces](https://github.com/mike-ap/kitty-workspaces) support.

<!-- markdownlint-disable MD034 -->

https://github.com/user-attachments/assets/a824eb3d-98f7-48c0-820f-cb8d9465bad8

<!-- markdownlint-enable MD034 -->

The picker lists individual windows. When Kitty Workspaces is present, it
instead lists workspaces.

## Installation

### Requirements and compatibility

| Component | Support policy                                                                                                                           |
| --------- | ---------------------------------------------------------------------------------------------------------------------------------------- |
| Kitty     | 0.50.0 is the initial supported and tested baseline. Older versions are unsupported; newer versions are best effort until tested.        |
| fzf       | Required on PATH. Version 0.72.0 is tested. Older versions need to support the picker options; they are not part of the tested baseline. |
| Linux     | Tested platform.                                                                                                                         |
| macOS     | Experimental; full validation on a Mac is pending.                                                                                       |

### Install the latest release

```sh
curl -fsSL https://github.com/mike-ap/kitty-workspace-picker/releases/latest/download/bootstrap.sh | sh
```

For a specific version or Kitty configuration directory:

```sh
curl -fsSL https://github.com/mike-ap/kitty-workspace-picker/releases/latest/download/bootstrap.sh | sh -s -- --version 0.1.0 --config-dir /path/to/kitty
```

### Install from a checkout or local archive

Run from a checkout or an extracted release archive:

```sh
sh install.sh
# Or use a custom Kitty configuration directory:
sh install.sh --config-dir /path/to/kitty
```

## Usage

Installation creates only the `kitty_workspace_picker/` package in Kitty’s
configuration root. Add this suggested binding to `kitty.conf`:

```conf
map ctrl+shift+p kitten kitty_workspace_picker/kitten.py
```

You can choose a different Kitty key combination. Then restart Kitty. The picker
receives a dedicated control channel from Kitty, including for provider reads; globally enabled remote
control is not required.

Example:

```text
map ctrl+shift+p kitten kitty_workspace_picker/kitten.py
map ctrl+shift+m kitten kitty_workspace_picker/kitten.py merge
map ctrl+shift+d kitten kitty_workspace_picker/kitten.py send
```

The picker lists only tabs and panes in the OS window where it was opened. The
kitten also accepts `merge` and `send` arguments, which you can bind to
shortcuts of your choice:

- `kitten kitty_workspace_picker/kitten.py merge`: select a pane from another
  tab and bring it into the originating tab using the splits layout.
- `kitten kitty_workspace_picker/kitten.py send`: select another tab to receive
  the originating pane. Enter moves it there; Ctrl+N creates or reuses a tab
  whose exact name is the query with surrounding whitespace removed. Escape
  cancels without moving anything.

Both movement modes work without Kitty Workspaces; metadata enriches their
labels when available. They exclude the originating tab from the selection list.
Sending to an existing tab selected from the list switches that tab to the splits
layout. With no other tabs, `send` still opens so Ctrl+N can create a destination.
The name must be nonempty and contain no terminal control characters.

Destinations stay within the originating OS window. Existing targets are
identified by tab ID, independently of changing display names. Moves run after
the picker overlay closes, through Kitty's kitten API; no global remote control
setting is required. A destination or source that disappears cancels the move.

With the default fzf controls, press Enter to focus a selection, or Escape/Ctrl+C
to close it; the keybinding works again after it exits. Ctrl+P/Ctrl+N and arrow
keys navigate, and Ctrl+U/Ctrl+K retain their query-editing behavior. In `send`
mode, Ctrl+N instead creates or reuses a named tab; use the arrow keys to navigate.

In focus mode, when Kitty Workspaces supplies `last_visited_order`, workspaces are
ordered by most recent visit, followed by unvisited workspaces in provider order,
with the current workspace last. Without Kitty Workspaces, provider order is kept.
Fuzzy match quality takes precedence; input order breaks ties. Window fallback
and movement modes retain Kitty's tab/pane order.

Workspace rows show the manual name, representative session title, worktree, or
workspace name (in that priority order), followed by project, representative
agent, and the provider's aggregate native program status: `○ idle`, `● working`,
`✓ done`, `? blocked`, `! error`, or `— unknown`. Details show each agent pane's
state and foreground process ID. There are no separate attention categories,
turn outcomes, conversation IDs, or unread-completion fields.

Kitty owns the lifetime of OSC 7501 reports. Done/error records clear when their
pane receives focus; transient records clear on process exit or a new shell
prompt. A pane without a report is Unknown. The picker displays the provider's
reports and does not infer additional agent state.

The details preview shows paths, branch, all sessions, and every pane, including
panes without agents. The workspace provider's active pane is marked `*`.
The preview is hidden by default. Press Ctrl+/ (also encoded as Ctrl+\_) to show or hide it. When shown, it
sits on the right in wide windows and below the list when space is narrow.
Press F2 to toggle the debug preview, which shows the
selected workspace’s complete state entry as formatted JSON (or the window entry
in fallback mode). Use Alt+J/K to scroll the preview down/up, or Alt+F/B to scroll
by page.

Rows, details, and debug data are captured once when the picker opens and stay
fixed until it closes. There is no polling or manual refresh. Reopen the picker
to see updated state.

The picker ignores `FZF_DEFAULT_OPTS` and `FZF_DEFAULT_OPTS_FILE`. To supply
picker-specific fzf defaults, set `KITTY_WORKSPACE_PICKER_FZF_OPTS` in the
environment inherited by Kitty. The picker's explicit command-line options still
apply.

## Update

Rerun the stable download command or update your checkout and repeat
[installation](#installation), then restart Kitty.

## Uninstall

Remove the picker binding from `kitty.conf`, then run from a checkout or
extracted release:

```sh
sh install.sh --uninstall
```

Or use the stable installer:

```sh
curl -fsSL https://github.com/mike-ap/kitty-workspace-picker/releases/latest/download/bootstrap.sh | sh -s -- --uninstall
```

Use `--config-dir /path/to/kitty` for a custom configuration directory, and
restart Kitty afterward.

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for bug reports, local checks, and release
preparation, and [CHANGELOG.md](CHANGELOG.md) for user-visible changes.

## License

Copyright (c) 2026 Michael Apicelli. Licensed under the [MIT License](LICENSE).
