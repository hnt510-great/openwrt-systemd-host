#!/bin/sh
# Publish only APKs that changed after a successful build.
set -eu

feed_tree=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
exec python3 "$feed_tree/scripts/build-and-publish.py" \
    --config "$feed_tree/configs/lan-apk-feeds.json" --incremental "$@"
