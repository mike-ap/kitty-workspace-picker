# Kitty Workspace Picker

An [fzf](https://github.com/junegunn/fzf) picker for Kitty windows, with [Kitty
Workspaces](https://github.com/mike-ap/kitty-workspaces) support.

<!-- markdownlint-disable MD034 -->

https://github.com/user-attachments/assets/a824eb3d-98f7-48c0-820f-cb8d9465bad8

<!-- markdownlint-enable MD034 -->

The picker lists individual windows. When Kitty Workspaces is present, it
lists workspaces instead of windows.

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

- `kitten kitty_workspace_picker/kitten.py merge`: select a pane from another
  tab and bring it into the originating tab using the splits layout.
- `kitten kitty_workspace_picker/kitten.py send`: select another tab to receive
  the originating pane. Enter moves it there; Ctrl+N creates or reuses a tab
  whose exact name is the query with surrounding whitespace removed. Escape
  cancels without moving anything.

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
