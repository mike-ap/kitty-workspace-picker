shell_files := "bootstrap.sh install.sh .envrc scripts/kitty-stock.sh"

check:
    just format-check
    just lint
    just test

format:
    uv run --locked ruff format .
    shfmt -w {{shell_files}}
    uv run --locked mdformat *.md
    markdownlint-cli2 --fix

format-check:
    uv run --locked ruff format --check .
    shfmt -d {{shell_files}}
    uv run --locked mdformat --check *.md

lint:
    uv run --locked ruff check .
    shellcheck {{shell_files}}
    markdownlint-cli2

test:
    uv run --locked pytest -q

# Build and verify the source archive in dist/ using Kitty's interpreter.
dist:
    uv build --sdist
    uv run --locked python scripts/check_dist.py

# Prepare and commit a release, then push its branch and annotated tag to origin.
[positional-arguments]
release version:
    uv run --locked python scripts/release.py "$1"

# Install the local checkout or extracted release into Kitty's config directory.
install:
    sh install.sh

# Remove installed project files; configuration entries are managed manually.
uninstall:
    sh install.sh --uninstall

# Launch a separate Kitty using defaults and the picker shortcut.
stock:
    sh scripts/kitty-stock.sh

# Branch coverage for Python running in pytest; Kitty subprocesses are separate.
coverage:
    uv run --locked pytest -q --cov --cov-report=term-missing --cov-report=xml --cov-report=html
