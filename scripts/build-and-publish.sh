#!/bin/sh
# Build from this checkout; publish only after make succeeds.
set -eu
feed_tree=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
cd "$feed_tree"
exec python3 "$feed_tree/scripts/build-and-publish.py" build "$@"
