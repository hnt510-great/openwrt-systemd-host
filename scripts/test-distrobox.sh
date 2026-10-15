#!/bin/sh
# Run from a fresh ordinary-user login. KEEP=1 retains only this test's resources.
set -eu

test "$(id -u)" -ne 0
test -n "${XDG_RUNTIME_DIR:-}"
test "$(podman info --format '{{.Host.Security.Rootless}}')" = true
getent passwd "$(id -u)"
getent group "$(id -g)"
env -u HOME -u SHELL distrobox list >/dev/null

image=${1:-docker.io/library/debian:13}
work=$(mktemp -d "${HOME}/.distrobox-test.XXXXXXXX")
name=distrobox-test-$(id -u)-${work##*.}
created=0
cleanup()
{
	status=$?
	trap - EXIT
	if [ "${KEEP:-0}" != 1 ]; then
		if [ "$created" = 1 ] && ! distrobox rm --force "$name"; then
			status=1
		fi
		rm -rf -- "$work"
	fi
	exit "$status"
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' HUP TERM

mkdir -p "$work/home" "$work/bin"
printf 'DISTROBOX_TEST_NAME=%s\nDISTROBOX_TEST_WORK=%s\n' "$name" "$work"
if podman container exists "$name"; then
	printf >&2 'FAIL: refusing to reuse existing container %s\n' "$name"
	exit 1
fi
created=1
distrobox create --yes --no-entry --name "$name" --image "$image" \
	--home "$work/home" --additional-packages jq
enter()
{
	distrobox enter --no-tty --no-workdir --name "$name" -- "$@"
}

enter sh -ec 'test "$(id -u)" = "$1"; test "$(id -g)" = "$2"; test "$HOME" = "$3"' \
	sh "$(id -u)" "$(id -g)" "$work/home"
printf '%s\n' 'host-to-container' > "$work/home/shared"
enter sh -ec 'test "$(cat "$HOME/shared")" = host-to-container; printf "%s\n" container-to-host > "$HOME/shared"'
test "$(cat "$work/home/shared")" = container-to-host
test "$(stat -c %u:%g "$work/home/shared")" = "$(id -u):$(id -g)"
enter sh -ec 'getent ahostsv4 example.com; curl --fail --silent --show-error -o /dev/null https://example.com'
enter sudo -n env DEBIAN_FRONTEND=noninteractive apt-get -y --no-install-recommends install hello
enter hello --greeting='Distrobox guest package installation passed'
enter distrobox-host-exec --yes sh -ec 'test "$(id -u)" = "$1"; test -r /etc/openwrt_release; getent passwd "$1"' sh "$(id -u)"
enter distrobox-export --bin /usr/bin/jq --export-path "$work/bin"
literal='spaces $dollar ; literal'
test "$("$work/bin/jq" -nr --arg text "$literal" '$text')" = "$literal"
if enter sh -c 'exit 37'; then
	printf >&2 '%s\n' 'FAIL: container command exit status was lost'
	exit 1
else
	test "$?" = 37
fi

distrobox list | grep -F "$name"
distrobox stop --yes "$name"
test "$(podman inspect --format '{{.State.Running}}' "$name")" = false
enter sh -ec 'test "$(cat "$HOME/shared")" = container-to-host; jq --version; hello --version | head -n 1'
printf '%s\n' 'PASS: rootless Distrobox lifecycle, identity, files, networking, guest packages, host commands and exports'
