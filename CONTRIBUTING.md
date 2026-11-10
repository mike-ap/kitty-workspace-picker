# Contributing

For bug reports, include your operating system, Kitty and fzf versions, the
project version or checkout revision, and steps to reproduce the problem.
Include the workspace provider version when one is installed. Describe the
expected result and the result you observed, with the relevant configuration
and logs.

## Local checks

Enter `devenv shell` (or allow direnv) for Python 3.12, uv, just, ShellCheck,
shfmt, markdownlint-cli2, and Lefthook. Shell entry installs the Git pre-commit
hook, which runs `just check` against the whole checkout. Commit from this
environment so all tools are on PATH. Outside devenv, install those tools and run
`lefthook install` once after cloning.

```sh
uv sync --locked
just check
```

`just check` verifies Python, shell, and Markdown formatting, runs Ruff, ShellCheck, and
markdownlint-cli2, then runs the tests. CI runs the same command on branch pushes,
pull requests, and release tags. The pre-commit hook checks without rewriting
files; use `just format` to apply Python, shell, and Markdown formatting and fixes.
Markdown formatting uses uv-managed mdformat with GitHub Markdown support on the
root-level `*.md` documentation files.
Shell formatting follows `.editorconfig`; Markdown rules live in
`.markdownlint-cli2.jsonc`, which the Neovim markdownlint-cli2 integration also reads.

Install fzf on PATH for the manual smoke test. Automated selection tests use
fixtures; they do not establish compatibility with an installed fzf.

For a manual smoke test, install Kitty and fzf, then run:

```sh
sh scripts/kitty-stock.sh
```

The launcher opens a separate Kitty instance with a temporary configuration.
Check selection, cancellation, preview controls, and repeated invocations.
The stock configuration binds only focus mode. To check movement, add these
bindings to an isolated test configuration with the picker installed:

```conf
map <merge-shortcut> kitten kitty_workspace_picker/kitten.py merge
map <send-shortcut> kitten kitty_workspace_picker/kitten.py send
```

Replace the shortcut placeholders with your preferred key combinations.
Use several tabs to check merging a pane, sending a pane to an existing tab,
Ctrl+N creating or reusing a named tab, and cancellation. Also check that another
OS window's panes never appear as destinations. Global remote control need not
be enabled for these bindings.
Changes to workspace metadata should also be tried with Kitty Workspaces,
including MRU ordering, fixed rows and previews, and collector-health explanations.

Python lint rules are explicitly selected in `pyproject.toml`, following
[Astral's rule-selection guidance](https://docs.astral.sh/ruff/linter/#rule-selection).
Both workspace projects use the same stable Ruff rule groups for correctness,
modern Python, imports, simplification, comprehensions, redundant code, return
paths, performance, and precise suppression comments. Preview rules are disabled;
layout is enforced by `ruff format`. Run `uv run --locked ruff check .` to lint
source, scripts, examples (where present), and tests with the locked Ruff version.

## Manual compatibility checks

Use the [README compatibility table](README.md#requirements-and-compatibility)
as the baseline. Before a release or when testing a new dependency version:

1. Record the operating system and the output of `kitty --version`,
   `kitty +runpy 'import sys; print(sys.version)'`, `fzf --version`, and
   `uv run --locked python --version`.
1. Run the local checks. Record the manual fzf smoke test separately.
1. Run the stock-Kitty smoke test above for individual-window mode. Repeat with
   Kitty Workspaces installed for workspace mode, recording the provider version
   or revision and verifying rows, previews, query, and selected target stay stable.
1. When testing an older fzf, check that the picker opens, accepts selections,
   cancels, and displays previews.
1. Record the revision, commands, and results in the pull request or release
   notes. Update the tested versions in the README only after validation passes.

macOS support is experimental. Run these checks in a Mac desktop session before
proposing a change to that status; validation on Linux does not cover macOS.

## Changes

Keep changes focused and add regression coverage for behavior changes. Update
the README when configuration or behavior changes, and add user-visible changes
to the Unreleased section of [CHANGELOG.md](CHANGELOG.md).

Keep individual-window selection working without a workspace provider. Preserve
compatibility with the documented versioned metadata contract and keep status
classification in the provider. For contract changes, also run `just check` in
the sibling `kitty-workspaces` checkout and test both together. Verify supported
version-1 metadata as well as absent, invalid, and timed-out provider fallbacks.

## Release preparation

Source archives are the supported release artifact. Keep changelog entries under
Unreleased until preparing a release. Set the version in `pyproject.toml`, update
the lockfile with `uv lock`, and move the release's changelog entries into a dated
version section. Run the checks and smoke tests above, then:

```sh
just dist
```

This runs `uv build --sdist` and
`uv run --locked python scripts/check_dist.py`, producing and verifying
`dist/kitty_workspace_picker-VERSION.tar.gz`. Kitty and uv must be on PATH. The
check compares the archive with the checkout, extracts it outside the checkout,
installs into a temporary Kitty configuration from an unrelated directory,
checks that existing configuration survives, and loads the installed package
and entry point under Kitty's interpreter. Unlike optional runtime tests,
release verification fails if Kitty is unavailable.

Use a dated changelog heading exactly like `## 0.1.0 - 2026-11-04`. Commit the
prepared source, then run:

```sh
just release 0.1.0
```

`just release VERSION` validates the version and dated notes, requires a clean
checkout on a branch with an `origin` remote, and rejects an existing local or
remote tag. It runs `just check` and `just dist`, creates an annotated `vVERSION`
tag, then atomically pushes the current branch and tag to `origin`. It does not
bump versions, edit the changelog, or make commits. Complete manual compatibility
checks before running it. If the push fails, the local tag remains; resolve the
reported problem and push the branch and tag together, or delete the local tag
before retrying the command.

The tag-triggered `.github/workflows/release.yml` installs Kitty 0.50.0, runs the
checks, builds and verifies the source archive, and validates that the stable
`vMAJOR.MINOR.PATCH` tag matches `pyproject.toml` and has dated changelog notes.
A separate publishing job creates the GitHub release only after verification.
Manual compatibility checks still happen before tagging. Prereleases are not
supported by this workflow.

Release assets are the source archive (with a stable project-based filename),
`SHA256SUMS`, and `bootstrap.sh`. The workflow renders the bootstrap template with
`github.repository` and the release tag. Thus the permanent
`releases/latest/download/bootstrap.sh` URL installs a complete, pinned release
without mixing files from different releases. `--version VERSION` selects an
older release; rerunning the default URL updates to the latest published release.
The download step uses the same `install.sh` verified by `just dist`.

No credentials or GitHub CLI are required on users' machines.
Rebuild and verify after any source or documentation change. Wheel/PyPI
publishing is deferred. The metadata protocol version is independent of the
project release version.

## License

Contributions are made under the project's [MIT license](LICENSE).

## Coverage

Run `just coverage` for branch-inclusive terminal, XML (`coverage.xml`), and
HTML (`htmlcov/index.html`) reports. CI uploads these reports as the `coverage`
artifact. Coverage measures Python in pytest, including runpy entry points;
separate Kitty processes and shell installers are exercised by tests but are
not instrumented. Missing lines remain visible; no coverage exclusions hide
Kitty entry points.
