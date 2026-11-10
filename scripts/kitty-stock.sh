#!/bin/sh
# Try the picker in a separate Kitty instance with an isolated configuration.
set -eu

source_dir=$(CDPATH='' cd -P "$(dirname "$0")/.." && pwd -P)
config_dir=$(mktemp -d "${TMPDIR:-/tmp}/kitty-picker-stock.XXXXXX")
trap 'rm -rf "$config_dir"' EXIT
trap 'exit 130' INT
trap 'exit 143' TERM

sh "$source_dir/install.sh" --config-dir "$config_dir"
cp "$source_dir/config/stock.conf" "$config_dir/kitty.conf"
KITTY_CONFIG_DIRECTORY=$config_dir kitty --config "$config_dir/kitty.conf" "$@"
