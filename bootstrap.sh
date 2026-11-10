#!/bin/sh
# Download a published release and run its installer. No Git or system Python needed.
# Release preparation embeds the repository and tag below.
set -eu

bootstrap_main() {
    repository='@REPOSITORY@'
    tag='@TAG@'
    config_dir=
    uninstall=false
    while [ "$#" -gt 0 ]; do
        case $1 in
            --version | --repository | --config-dir)
                [ "$#" -ge 2 ] || {
                    echo "Missing value for $1" >&2
                    return 2
                }
                case $1 in
                    --version) tag=v${2#v} ;;
                    --repository) repository=$2 ;;
                    --config-dir) config_dir=$2 ;;
                esac
                shift 2
                ;;
            --uninstall)
                uninstall=true
                shift
                ;;
            *)
                echo "Usage: sh -s -- [--version VERSION] [--config-dir PATH] [--uninstall] [--repository OWNER/REPO]" >&2
                return 2
                ;;
        esac
    done
    case $repository in
        '' | *[!A-Za-z0-9_./-]* | /* | */ | *..*)
            echo "Invalid or unset repository" >&2
            return 2
            ;;
    esac
    case $repository in
        */*) : ;;
        *)
            echo "Expected OWNER/REPO" >&2
            return 2
            ;;
    esac
    version=${tag#v}
    case $version in
        '' | *[!0-9A-Za-z.+-]* | [!0-9]*)
            echo "Invalid or unset release version" >&2
            return 2
            ;;
    esac
    command -v curl >/dev/null
    command -v tar >/dev/null
    if command -v sha256sum >/dev/null; then
        checksum=sha256sum
    elif command -v shasum >/dev/null; then
        checksum=shasum
    else
        echo "Install sha256sum or shasum to verify the download" >&2
        return 1
    fi
    temporary=$(mktemp -d "${TMPDIR:-/tmp}/kitty-workspace-picker-install.XXXXXX")
    trap 'rm -rf -- "$temporary"' EXIT
    trap 'exit 130' INT
    trap 'exit 143' TERM
    base=https://github.com/$repository/releases/download/$tag
    curl -fSL --retry 3 "$base/kitty-workspace-picker.tar.gz" -o "$temporary/archive.tar.gz"
    curl -fSL --retry 3 "$base/SHA256SUMS" -o "$temporary/SHA256SUMS"
    expected=$(awk '$2 == "kitty-workspace-picker.tar.gz" {print $1}' "$temporary/SHA256SUMS")
    case $expected in
        '' | *[!0-9a-f]*)
            echo "Invalid release checksum" >&2
            return 1
            ;;
    esac
    [ "${#expected}" -eq 64 ] || {
        echo "Invalid release checksum" >&2
        return 1
    }
    if [ "$checksum" = sha256sum ]; then
        actual=$(sha256sum "$temporary/archive.tar.gz")
    else
        actual=$(shasum -a 256 "$temporary/archive.tar.gz")
    fi
    [ "${actual%% *}" = "$expected" ] || {
        echo "Release checksum mismatch" >&2
        return 1
    }
    tar -xzf "$temporary/archive.tar.gz" -C "$temporary"
    source=$temporary/kitty_workspace_picker-$version
    [ -f "$source/install.sh" ] || {
        echo "Incomplete release archive" >&2
        return 1
    }
    set --
    if [ -n "$config_dir" ]; then set -- "$@" --config-dir "$config_dir"; fi
    if [ "$uninstall" = true ]; then set -- "$@" --uninstall; fi
    sh "$source/install.sh" "$@"
}

# Keep execution after the complete function definition when piped to sh.
bootstrap_main "$@"
