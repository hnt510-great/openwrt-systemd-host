#!/bin/sh

set -eu

usage() {
	cat <<'EOF'
Usage: update-prebuilt-packages.sh [--check|--update]

  --check   Report available updates without modifying files.
            Exit 1 when an update is available, otherwise exit 0.
  --update  Update package versions and hashes atomically (default).
EOF
}

mode=update
case "${1:-}" in
	"") ;;
	--check) mode=check ;;
	--update) mode=update ;;
	--help|-h)
		usage
		exit 0
		;;
	*)
		usage >&2
		exit 2
		;;
esac

for command in curl jq awk grep mktemp cmp mv chmod; do
	command -v "$command" >/dev/null 2>&1 || {
		echo "error: required command not found: $command" >&2
		exit 2
	}
done

script_dir=$(CDPATH= cd -P "$(dirname "$0")" && pwd)
custom_dir=$(CDPATH= cd -P "$script_dir/.." && pwd)
cmake_makefile="$custom_dir/cmake-bin/Makefile"
node_makefile="$custom_dir/node-bin/Makefile"

update_tmp=$(mktemp -d "${TMPDIR:-/tmp}/update-prebuilt-packages.XXXXXX")
cleanup() {
	rm -rf "$update_tmp"
}
trap cleanup 0
trap 'exit 1' HUP INT TERM

fetch() {
	curl --fail --silent --show-error --location \
		--retry 3 --retry-delay 1 \
		--user-agent openwrt-prebuilt-package-updater \
		"$1"
}

validate_version() {
	printf '%s\n' "$2" | grep -Eq '^[0-9]+\.[0-9]+\.[0-9]+$' || {
		echo "error: invalid $1 version: $2" >&2
		exit 2
	}
}

validate_hash() {
	printf '%s\n' "$2" | grep -Eq '^[0-9a-f]{64}$' || {
		echo "error: invalid $1 SHA-256: $2" >&2
		exit 2
	}
}

cmake_release_json="$update_tmp/cmake-release.json"
fetch https://api.github.com/repos/Kitware/CMake/releases/latest > "$cmake_release_json"
cmake_version=$(jq -er \
	'select(.draft == false and .prerelease == false) | .tag_name | ltrimstr("v")' \
	"$cmake_release_json")
validate_version CMake "$cmake_version"

cmake_archive="cmake-$cmake_version-linux-x86_64.tar.gz"
cmake_checksums="$update_tmp/cmake-sha256.txt"
fetch "https://github.com/Kitware/CMake/releases/download/v$cmake_version/cmake-$cmake_version-SHA-256.txt" \
	> "$cmake_checksums"
cmake_hash=$(awk -v archive="$cmake_archive" \
	'$2 == archive { print $1; found = 1; exit } END { if (!found) exit 1 }' \
	"$cmake_checksums")
validate_hash CMake "$cmake_hash"

node_index="$update_tmp/node-index.json"
fetch https://nodejs.org/dist/index.json > "$node_index"
node_version=$(jq -er \
	'[.[] | select((.lts | type) == "string" and (.files | index("linux-x64")))] | first | .version | ltrimstr("v")' \
	"$node_index")
validate_version Node.js "$node_version"

node_archive="node-v$node_version-linux-x64.tar.xz"
node_checksums="$update_tmp/node-sha256.txt"
fetch "https://nodejs.org/dist/v$node_version/SHASUMS256.txt" > "$node_checksums"
node_hash=$(awk -v archive="$node_archive" \
	'$2 == archive { print $1; found = 1; exit } END { if (!found) exit 1 }' \
	"$node_checksums")
validate_hash Node.js "$node_hash"

updates=0

update_makefile() {
	package_name=$1
	makefile=$2
	new_version=$3
	new_hash=$4

	version_count=$(grep -c '^PKG_VERSION:=' "$makefile")
	hash_count=$(grep -c '^PKG_HASH:=' "$makefile")
	release_count=$(grep -c '^PKG_RELEASE:=' "$makefile")
	if [ "$version_count" -ne 1 ] || [ "$hash_count" -ne 1 ] || [ "$release_count" -ne 1 ]; then
		echo "error: unexpected package metadata layout: $makefile" >&2
		exit 2
	fi

	old_version=$(awk -F:= '/^PKG_VERSION:=/ { print $2 }' "$makefile")
	old_hash=$(awk -F:= '/^PKG_HASH:=/ { print $2 }' "$makefile")

	if [ "$old_version" = "$new_version" ] && [ "$old_hash" = "$new_hash" ]; then
		echo "$package_name: current ($new_version)"
		return
	fi

	updates=$((updates + 1))
	echo "$package_name: $old_version -> $new_version"
	if [ "$mode" = check ]; then
		return
	fi

	updated_makefile="$update_tmp/$package_name.Makefile"
	awk -v version="$new_version" -v hash="$new_hash" '
		/^PKG_VERSION:=/ { print "PKG_VERSION:=" version; next }
		/^PKG_RELEASE:=/ { print "PKG_RELEASE:=1"; next }
		/^PKG_HASH:=/ { print "PKG_HASH:=" hash; next }
		{ print }
	' "$makefile" > "$updated_makefile"
	chmod 0644 "$updated_makefile"

	if ! cmp -s "$makefile" "$updated_makefile"; then
		mv "$updated_makefile" "$makefile"
	fi
}

update_makefile cmake-bin "$cmake_makefile" "$cmake_version" "$cmake_hash"
update_makefile node-bin "$node_makefile" "$node_version" "$node_hash"

if [ "$mode" = check ] && [ "$updates" -ne 0 ]; then
	exit 1
fi
