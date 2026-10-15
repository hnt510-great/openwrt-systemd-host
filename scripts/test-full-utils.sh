#!/bin/sh
# Read-only system checks; test data and loopback listeners are temporary.
set -eu
work=$(mktemp -d /tmp/full-utils.XXXXXX)
listener=
cleanup() {
	[ -z "$listener" ] || kill "$listener" 2>/dev/null || :
	rm -rf "$work"
}
trap cleanup EXIT HUP INT TERM

for cmd in chvt clear hexdump logger nc netstat nslookup pidof ping6 reset setsid taskset time traceroute traceroute6 vi; do
	path=$(command -v "$cmd")
	[ "$cmd" != time ] || path=/usr/bin/time
	case "$(readlink -f "$path")" in
		*/busybox) echo "FAIL: $cmd still resolves to BusyBox" >&2; exit 1;;
	esac
done
for cmd in ash sh crontab fsync lock login netmsg resize; do
	[ "$(readlink -f "/usr/bin/$cmd")" = /usr/bin/busybox ]
done

printf '\000\001\177\377' > "$work/input"
test "$(hexdump -v -e '1/1 "%02x"' "$work/input")" = 00017fff
/usr/bin/time -f '%x' -o "$work/time" true
test "$(cat "$work/time")" = 0
if /usr/bin/time -o "$work/time" sh -c 'exit 23'; then exit 1; else test "$?" = 23; fi

pidof systemd | tr ' ' '\n' | grep -qx 1
for comm in procd netifd weston; do
	test "$(pidof "$comm" | tr ' ' '\n' | sort -n)" = "$(busybox pidof "$comm" | tr ' ' '\n' | sort -n)"
done
test "$(setsid -w sh -c 'ps -o sid= -p $$ | tr -d " "')" -gt 1
if setsid -w sh -c 'exit 17'; then exit 1; else test "$?" = 17; fi
taskset -p $$

vi -Nu NONE -n -es -c 'call setline(1, "standalone-vi")' -c "wq $work/vi"
grep -qx standalone-vi "$work/vi"
TERM=xterm-256color clear > "$work/clear"
test -s "$work/clear"
TERM=xterm-256color tput cols | grep -Eq '^[0-9]+$'
reset -V
chvt --version
hwclock --version
ifconfig lo | grep -q 127.0.0.1
netstat -ln | head -n 8
nslookup localhost 127.0.0.1 > "$work/dns"
ping6 -c 1 -W 2 ::1
traceroute -n -q 1 -m 1 -w 1 127.0.0.1
traceroute6 -n -q 1 -m 1 -w 1 ::1

# Exercise normal and receive-only listeners with both address families.
for variant in normal recv-only; do
for addr in 127.0.0.1 ::1; do
	port=$(python3 -c 'import socket; s=socket.socket(); s.bind(("127.0.0.1",0)); print(s.getsockname()[1]); s.close()')
	if [ "$variant" = recv-only ]; then
		setsid -w nc --recv-only -l "$addr" "$port" > "$work/nc" &
	else
		setsid -w nc -l "$addr" "$port" > "$work/nc" &
	fi
	listener=$!
	sleep 1
	printf '%s\n' standalone-nc | nc --send-only -w 2 "$addr" "$port"
	wait "$listener"
	listener=
	grep -qx standalone-nc "$work/nc"
done
done

marker="full-utils-$$"
logger -t full-utils "$marker"
sleep 1
logread -e "$marker" | grep -q "$marker"
for cmd in iptables iptables-nft iptables-restore iptables-save iptables-nft-restore iptables-nft-save iptables-restore-translate iptables-translate; do
	[ "$(readlink -f "/usr/sbin/$cmd")" = /usr/sbin/xtables-nft-multi ]
done
iptables --version | grep -q nf_tables
iptables-save > "$work/iptables"
printf '%s\n' 'PASS: standalone utilities, loopback networking, DNS, logging, exit status and retained OpenWrt helpers'
