#!/bin/sh
# Build from this checkout; publish only after make succeeds.
set -eu
feed_tree=$(CDPATH= cd "$(dirname "$0")/.." && pwd)
cd "$feed_tree"
make "$@"
exec "$feed_tree/scripts/publish-changed-feeds.sh"
