#!/bin/sh
# Update only the currently packaged ESR major branch; never migrate it silently.
set -eu

mode=${1:---check}
case "$mode" in
	--check|--update) ;;
	--help) echo 'Usage: update-firefox-esr.sh [--check|--update] (default: --check)'; exit 0 ;;
	*) echo 'Usage: update-firefox-esr.sh [--check|--update]' >&2; exit 2 ;;
esac

for tool in curl jq awk sort tail mktemp sha256sum cmp mv chmod; do
	command -v "$tool" >/dev/null 2>&1 || { echo "Missing host tool: $tool" >&2; exit 2; }
done
script_dir=$(CDPATH= cd -P "$(dirname "$0")" && pwd)
makefile="$script_dir/../firefox-esr-bin/Makefile"
for field in PKG_VERSION PKG_HASH PKG_RELEASE; do
	[ "$(awk -v field="$field" '$0 ~ "^" field ":=" { n++ } END { print n+0 }' "$makefile")" = 1 ] || {
		echo "Unexpected $field metadata" >&2; exit 2;
	}
done
old_version=$(awk -F:= '/^PKG_VERSION:=/ { print $2 }' "$makefile")
old_hash=$(awk -F:= '/^PKG_HASH:=/ { print $2 }' "$makefile")
major=${old_version%%.*}
case "$major" in ''|*[!0-9]*) echo 'Invalid packaged ESR major' >&2; exit 2 ;; esac

update_tmp=$(mktemp -d "${TMPDIR:-/tmp}/firefox-esr-update.XXXXXX")
trap 'rm -rf "$update_tmp"' 0
trap 'exit 1' HUP INT TERM
fetch() {
	curl --fail --silent --show-error --location --proto '=https' --proto-redir '=https' \
		--retry 3 --retry-delay 1 "$1"
}
fetch https://product-details.mozilla.org/1.0/firefox_versions.json > "$update_tmp/versions.json"
version=$(jq -er --arg major "$major" \
	'[.FIREFOX_ESR, .FIREFOX_ESR_NEXT] | map(select(type == "string") | select(test("^" + $major + "\\.[0-9]+(\\.[0-9]+)?esr$"))) | sort_by(sub("esr$"; "") | split(".") | map(tonumber)) | last // empty' \
	"$update_tmp/versions.json") || { echo "ESR $major is no longer advertised; review a major upgrade manually." >&2; exit 2; }
[ "$(printf '%s\n%s\n' "$old_version" "$version" | sort -V | tail -n 1)" = "$version" ] || {
	echo "Refusing ESR downgrade: $old_version -> $version" >&2; exit 2;
}
archive="firefox-$version.tar.xz"
release_url="https://archive.mozilla.org/pub/firefox/releases/$version"
fetch "$release_url/SHA256SUMS" > "$update_tmp/SHA256SUMS"
hash=$(awk -v file="linux-x86_64/zh-CN/$archive" '$2 == file { hash=$1; n++ } END { if (n != 1) exit 1; print hash }' "$update_tmp/SHA256SUMS")
printf '%s\n' "$hash" | awk 'length($0) == 64 && $0 !~ /[^0-9a-f]/ { valid=1 } END { exit !valid }' || {
	echo 'Invalid official Firefox SHA256' >&2; exit 2;
}
if [ "$version" = "$old_version" ] && [ "$hash" = "$old_hash" ]; then
	echo "firefox-esr-bin: current ($version)"
	exit 0
fi
echo "firefox-esr-bin: $old_version -> $version"
[ "$mode" = --update ] || exit 1
fetch "$release_url/linux-x86_64/zh-CN/$archive" > "$update_tmp/$archive"
printf '%s  %s\n' "$hash" "$update_tmp/$archive" | sha256sum -c -
# Stage beside the Makefile so the final rename is atomic across filesystems.
staged=$(mktemp "$makefile.update.XXXXXX")
trap 'rm -rf "$update_tmp"; [ -z "${staged:-}" ] || rm -f "$staged"' 0
awk -v version="$version" -v hash="$hash" '
	/^PKG_VERSION:=/ { print "PKG_VERSION:=" version; next }
	/^PKG_HASH:=/ { print "PKG_HASH:=" hash; next }
	/^PKG_RELEASE:=/ { print "PKG_RELEASE:=1"; next }
	{ print }
' "$makefile" > "$staged"
chmod 0644 "$staged"
mv "$staged" "$makefile"
staged=
echo 'Rebuild the package and firmware, then repeat dependency and VM validation before deployment.'
