# Changelog

User-visible changes are recorded here. Entries remain under Unreleased until
a release is tagged.

## Unreleased

- Simplify publishing with `just release VERSION`: update the project version and
  lockfile, move Unreleased notes into a dated changelog section, and commit the
  prepared release before tagging and pushing it.
- Keep release checks and source archive verification ahead of the release commit
  and tag. Failed checks leave prepared files available for inspection without
  publishing a release.
- Document the automated release workflow and recovery steps for failed checks
  or pushes.

## 0.1.0 - 2026-11-11

- initial release
