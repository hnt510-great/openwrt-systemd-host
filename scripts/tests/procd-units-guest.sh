#!/bin/sh
# Run as root inside a disposable native-systemd OpenWrt VM: procd units mode.
set -eu

fail() {
	echo "FAIL: $*" >&2
	exit 1
}

pass() {
	echo "PASS: $*"
}

wait_for() {
	n=0
	while ! sh -c "$1" >/dev/null 2>&1; do
		n=$((n + 1))
		[ "$n" -lt "${2:-100}" ] || fail "timeout: $1"
		sleep 0.2
	done
}

unit=openwrt-unitprobe@main.service

main_pid() {
	systemctl show -P MainPID "$unit"
}

cleanup() {
	/etc/init.d/unitprobe stop >/dev/null 2>&1 || true
	rm -f /etc/init.d/unitprobe /etc/config/unitprobe
	rm -f /etc/hotplug.d/mem/99-unitprobe /tmp/unitprobe-hotplug /tmp/unitprobe-error
	rmdir /etc/hotplug.d/mem 2>/dev/null || true
}
trap cleanup EXIT HUP INT TERM

[ "$(cat /proc/1/comm)" = systemd ] || fail "PID 1 is not systemd"
systemctl show -P ExecStart openwrt-procd.service | grep -q -- '--systemd=units' ||
	fail "procd is not in units mode"
pass "procd runs with --systemd=units"

ubus call system watchdog | grep -q '"owner": "systemd"' || fail "watchdog owner"
ubus call system watchdog '{"stop": true}' >/dev/null 2>&1 && fail "watchdog change accepted"
pass "system watchdog reports systemd and rejects changes"

# Every running instance maps to an active transient unit.
units=$(ubus call service list | jsonfilter -e '@[*].instances[*].systemd_unit' | sort -u)
[ -n "$units" ] || fail "no instance reports systemd_unit"
for u in $units; do
	systemctl is-active -q "$u" || systemctl show -P SubState "$u" | grep -q exited ||
		echo "note: $u is $(systemctl is-active "$u")"
done
pass "$(echo "$units" | wc -l) instances run as units"

# Router daemons are not procd children; only hotplug helpers may be.
procd_pid=$(systemctl show -P MainPID openwrt-procd.service)
children=""
for dir in /proc/[0-9]*; do
	ppid=$(awk '/^PPid:/ { print $2 }' "$dir/status" 2>/dev/null) || continue
	[ "$ppid" = "$procd_pid" ] || continue
	comm=$(cat "$dir/comm" 2>/dev/null) || continue
	case "$comm" in
		sh|hotplug-call|udevadm) ;;
		*) children="$children $comm" ;;
	esac
done
[ -z "$children" ] || fail "procd children:$children"
pass "no daemon is a procd child"

# A respawning probe service with a reload trigger.
cat > /etc/config/unitprobe <<'EOF'
config probe main
	option value 'one'
EOF
cat > /etc/init.d/unitprobe <<'EOF'
#!/bin/sh /etc/rc.common
USE_PROCD=1
start_service() {
	local value
	config_load unitprobe
	config_get value main value
	procd_open_instance main
	procd_set_param command /bin/sh -c 'echo "probe $PROBE_VALUE $0"; trap "echo hup" HUP; while :; do sleep 1; done' "$value"
	procd_set_param env PROBE_VALUE="$value"
	procd_set_param respawn 3600 1 3
	procd_set_param stdout 1
	procd_set_param limits nofile="512 1024"
	procd_set_param reload_signal HUP
	procd_close_instance
}
service_triggers() {
	procd_add_reload_trigger unitprobe
}
EOF
chmod +x /etc/init.d/unitprobe
/etc/init.d/unitprobe start
wait_for "systemctl is-active -q $unit"
[ "$(systemctl show -P Restart "$unit")" = always ] || fail "Restart"
[ "$(systemctl show -P RestartUSec "$unit")" = 1s ] || fail "RestartUSec"
[ "$(systemctl show -P StartLimitBurst "$unit")" = 4 ] || fail "StartLimitBurst"
[ "$(systemctl show -P LimitNOFILE "$unit")" = 1024 ] || fail "LimitNOFILE"
[ "$(systemctl show -P LimitNOFILESoft "$unit")" = 512 ] || fail "LimitNOFILESoft"
[ "$(systemctl show -P Slice "$unit")" = openwrt-unitprobe.slice ] || fail "Slice"
systemctl show -P Environment "$unit" | grep -q 'PROBE_VALUE=one' || fail "Environment"
wait_for "journalctl -u $unit -o cat | grep -q 'probe one one'"
ubus call service list '{"name":"unitprobe"}' | grep -q "\"systemd_unit\": \"$unit\"" ||
	fail "service list unit"
[ "$(ubus call service list '{"name":"unitprobe"}' | jsonfilter -e '@.unitprobe.instances.main.pid')" = "$(main_pid)" ] ||
	fail "service list pid"
pass "instance parameters map to unit properties"

# All client IPC paths must refuse a direct job without changing the instance.
pid=$(main_pid)
restarts=$(systemctl show -P NRestarts "$unit")
refused() {
	set +e
	output=$("$@" 2>&1)
	code=$?
	set -e
	[ "$code" = 4 ] || fail "expected exit 4, got $code: $output"
	echo "$output" | grep -q '/etc/init.d/unitprobe' || fail "missing init-script advice: $output"
	[ "$(main_pid)" = "$pid" ] || fail "refusal changed MainPID"
	[ "$(systemctl show -P NRestarts "$unit")" = "$restarts" ] || fail "refusal changed NRestarts"
}
for verb in stop restart start reload try-restart reload-or-restart reload-or-try-restart; do
	refused systemctl "$verb" "$unit"
done
[ "$(systemctl show -P CanStart "$unit")" = no ] || fail "CanStart"
[ "$(systemctl show -P CanStop "$unit")" = no ] || fail "CanStop"
[ "$(systemctl show -P RefuseManualStart "$unit")" = no ] || fail "RefuseManualStart"
[ "$(systemctl show -P RefuseManualStop "$unit")" = no ] || fail "RefuseManualStop"
# busctl does not map D-Bus errors to systemctl's exit status.
if busctl call org.freedesktop.systemd1 /org/freedesktop/systemd1 org.freedesktop.systemd1.Manager \
	StopUnit ss "$unit" replace > /tmp/unitprobe-error 2>&1; then
	fail "D-Bus StopUnit allowed"
fi
grep -q '/etc/init.d/unitprobe' /tmp/unitprobe-error || fail "D-Bus advice"
unit_path=$(busctl call org.freedesktop.systemd1 /org/freedesktop/systemd1 \
	org.freedesktop.systemd1.Manager GetUnit s "$unit" | cut -d '"' -f 2)
if busctl call org.freedesktop.systemd1 "$unit_path" org.freedesktop.systemd1.Unit \
	Stop s replace > /tmp/unitprobe-error 2>&1; then
	fail "D-Bus Unit.Stop allowed"
fi
grep -q '/etc/init.d/unitprobe' /tmp/unitprobe-error || fail "Unit.Stop advice"
bridge_pid=$(systemctl show -P MainPID openwrt-service-bridge.service)
if busctl call org.freedesktop.systemd1 /org/freedesktop/systemd1 org.freedesktop.systemd1.Manager \
	EnqueueUnitJobMany assst 2 openwrt-service-bridge.service "$unit" stop replace 0 > /tmp/unitprobe-error 2>&1; then
	fail "batch EnqueueUnitJob allowed"
fi
grep -q '/etc/init.d/unitprobe' /tmp/unitprobe-error || fail "batch advice"
[ "$(systemctl show -P MainPID openwrt-service-bridge.service)" = "$bridge_pid" ] || fail "batch changed another unit"
systemctl set-property openwrt-service-bridge.service Markers=needs-restart
systemctl set-property "$unit" Markers=needs-restart
if systemctl reload-or-restart --marked > /tmp/unitprobe-error 2>&1; then
	fail "marked instance allowed"
fi
if varlinkctl call /run/systemd/io.systemd.Manager io.systemd.Manager.EnqueueMarkedJobs '{}' \
	> /tmp/unitprobe-error 2>&1; then
	fail "varlink marked instance allowed"
fi
grep -q '/etc/init.d/unitprobe' /tmp/unitprobe-error || fail "varlink advice"
systemctl set-property "$unit" Markers=
systemctl set-property openwrt-service-bridge.service Markers=
[ "$(systemctl show -P MainPID openwrt-service-bridge.service)" = "$bridge_pid" ] || fail "marked jobs changed another unit"
[ "$(main_pid)" = "$pid" ] || fail "IPC refusal changed MainPID"
[ "$(systemctl show -P NRestarts "$unit")" = "$restarts" ] || fail "IPC refusal changed NRestarts"
ubus call service list '{"name":"unitprobe"}' | grep -q '"running": true' || fail "refusal lost procd running state"
journalctl -b -u "$unit" -o cat | grep -q 'Refused direct .* from PID' || fail "no refusal journal"
pass "direct jobs refused through systemctl, D-Bus, batch and marked paths"
/etc/init.d/unitprobe restart
wait_for "systemctl is-active -q $unit && [ \"\$(systemctl show -P MainPID $unit)\" != $pid ]"
pid=$(main_pid)
/etc/init.d/unitprobe stop
wait_for "! systemctl is-active -q $unit"
wait_for "[ \"\$(systemctl show -P LoadState $unit)\" = not-found ]"
set +e
output=$(systemctl start "$unit" 2>&1)
code=$?
set -e
[ "$code" = 4 ] || fail "missing-unit start exit $code: $output"
echo "$output" | grep -q 'is not running; procd creates' || fail "missing-unit advice"
/etc/init.d/unitprobe start
wait_for "systemctl is-active -q $unit"
set +e
output=$(systemctl restart netifd 2>&1)
code=$?
set -e
[ "$code" != 0 ] || fail "plain name unexpectedly succeeded"
echo "$output" | grep -q 'systemctl restart openwrt@network' || fail "netifd hint: $output"
pass "init-script controls still work, stopped instance refused, bare name hinted"

pid=$(main_pid)
/etc/init.d/unitprobe reload
sleep 2
[ "$(main_pid)" = "$pid" ] || fail "reload of an unchanged config restarted the process"
pass "reload of an unchanged config keeps the process"

# reload_config sends this event for each changed package; on a fresh overlay
# it would also reload every other package, so send just this one.
config_changed() {
	ubus call service event '{"type":"config.change","data":{"package":"unitprobe"}}'
}

# As with procd, a changed instance with reload_signal is signalled, not restarted.
uci set unitprobe.main.value=two
uci commit unitprobe
config_changed
wait_for "journalctl -u $unit -o cat | grep -q '^hup$'"
[ "$(main_pid)" = "$pid" ] || fail "reload_signal instance was restarted"
pass "config.change trigger sends reload_signal"

systemctl kill -s KILL "$unit"
wait_for "[ \"\$(systemctl show -P NRestarts $unit)\" -ge 1 ] && systemctl is-active -q $unit"
[ "$(main_pid)" != "$pid" ] || fail "no respawn"
wait_for "[ \"\$(ubus call service list '{\"name\":\"unitprobe\"}' | jsonfilter -e '@.unitprobe.instances.main.respawn_count')\" -ge 1 ]"
pass "systemd respawned a killed daemon and procd reports respawn_count"

# The restart decision uses the running instance's reload_signal, so drop it
# with a restart before testing replacement on a configuration change.
sed -i '/reload_signal/d' /etc/init.d/unitprobe
/etc/init.d/unitprobe restart
wait_for "systemctl is-active -q $unit && ! ubus call service list '{\"name\":\"unitprobe\"}' | grep -q reload_signal"
pid=$(main_pid)
uci set unitprobe.main.value=three
uci commit unitprobe
config_changed
wait_for "journalctl -u $unit -o cat | grep -q 'probe three three'"
[ "$(main_pid)" != "$pid" ] || fail "config change kept the old process"
systemctl show -P Environment "$unit" | grep -q 'PROBE_VALUE=three' || fail "new Environment"
pass "UCI change without reload_signal replaces the unit"

/etc/init.d/unitprobe stop
wait_for "! systemctl is-active -q $unit"
wait_for "[ -z \"\$(ubus call service list '{\"name\":\"unitprobe\"}' | jsonfilter -e '@.unitprobe.instances.main')\" ]"
pass "stop removes the unit and the instance"

/etc/init.d/unitprobe start
wait_for "systemctl is-active -q $unit"
systemctl stop openwrt-unitprobe.slice
wait_for "! systemctl is-active -q $unit"
/etc/init.d/unitprobe stop
pass "whole-service slice stop remains an override"

# Crash loop: retry 2 gives up after three quick failures.
sed -i "s|procd_set_param command .*|procd_set_param command /bin/sh -c 'exit 3'|; s|respawn 3600 1 3|respawn 3600 0 2|" \
	/etc/init.d/unitprobe
/etc/init.d/unitprobe start
wait_for "journalctl -b -u openwrt-procd.service -o cat | grep -q 'unitprobe::main s in a crash loop'" 150
code=$(ubus call service list '{"name":"unitprobe"}' | jsonfilter -e '@.unitprobe.instances.main.exit_code')
[ "$code" = 3 ] || fail "crash-loop exit_code $code"
/etc/init.d/unitprobe stop
pass "crash loop stops after the retry limit with the daemon exit code"

# udev forwards device events to the OpenWrt handlers.
mkdir -p /etc/hotplug.d/mem
cat > /etc/hotplug.d/mem/99-unitprobe <<'EOF'
echo "$ACTION $DEVNAME $SUBSYSTEM" >> /tmp/unitprobe-hotplug
EOF
sleep 1
udevadm trigger --action=change --settle /sys/class/mem/null
wait_for "grep -qx 'change null mem' /tmp/unitprobe-hotplug"
[ "$(wc -l < /tmp/unitprobe-hotplug)" = 1 ] || fail "event handled more than once"
pass "udev event reached /etc/hotplug.d once, with kernel-style DEVNAME"

[ -e /run/procd-udev-coldplug ] || fail "coldplug marker"

# Restarting procd stops its units (BindsTo), reruns the rc sequence and
# starts them again.
before=$(systemctl show -P MainPID openwrt-dnsmasq@cfg01411c.service)
systemctl restart openwrt-procd.service
wait_for "systemctl is-active -q openwrt-services.service" 900
wait_for "ubus call service list '{\"name\":\"dnsmasq\"}' | grep -q '\"running\": true'" 300
after=$(systemctl show -P MainPID openwrt-dnsmasq@cfg01411c.service)
[ "$after" != 0 ] && [ "$after" != "$before" ] || fail "dnsmasq after procd restart"
pass "procd restart restarts its units"
journalctl -b -u openwrt-procd.service -o cat | grep 'without a unit' || true
pass "procd units-mode guest checks"
