#!/usr/bin/env python3
"""Exercise procd/libudev/Weston hotplug in an already booted disposable QEMU VM.

Requires root SSH, Python ctypes, libinput tools, and an xHCI bus named
hotplug-usb. Creates a temporary desktop account and installs a delayed input
hook in the guest; never run against a production machine. See docs/input-hotplug.md.
"""

import argparse
import base64
import json
from pathlib import Path
import secrets
import shlex
import socket
import subprocess
import time


class QMP:
    def __init__(self, path):
        self.socket = socket.socket(socket.AF_UNIX)
        self.socket.connect(str(path))
        self.socket.settimeout(15)
        self.stream = self.socket.makefile("rb")
        self.stream.readline()
        self.command("qmp_capabilities")

    def command(self, command, arguments=None):
        request = {"execute": command}
        if arguments is not None:
            request["arguments"] = arguments
        self.socket.sendall(json.dumps(request).encode() + b"\n")
        while True:
            reply = json.loads(self.stream.readline())
            if "error" in reply:
                raise RuntimeError(reply)
            if "return" in reply:
                return reply["return"]

    def close(self):
        self.stream.close()
        self.socket.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--ssh-port", type=int, required=True)
    parser.add_argument("--identity", type=Path, required=True)
    parser.add_argument("--qmp", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--no-desktop", action="store_true", help="Probe procd recovery without Weston")
    args = parser.parse_args()
    args.output.mkdir(parents=True, exist_ok=True)
    ssh = [
        "ssh", "-i", str(args.identity), "-p", str(args.ssh_port),
        "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=no",
        "-o", "UserKnownHostsFile=/dev/null", "-o", "LogLevel=ERROR",
        "-o", "ConnectTimeout=5", "root@127.0.0.1",
    ]

    def run(command, input_data=None, timeout=40):
        result = subprocess.run(
            ssh + ["sh -c " + shlex.quote(command)], input=input_data,
            stdout=subprocess.PIPE, stderr=subprocess.PIPE, timeout=timeout,
        )
        if result.returncode:
            raise RuntimeError(result.stderr.decode() + result.stdout.decode())
        return result.stdout.decode()

    def upload(path, content):
        encoded = base64.b64encode(content).decode()
        run("printf '%s' " + shlex.quote(encoded) + " | base64 -d > " + shlex.quote(path))

    def wait(predicate, timeout=35):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            value = predicate()
            if value:
                return value
            time.sleep(0.25)
        raise TimeoutError("Guest condition did not become true")

    def records():
        return [json.loads(line) for line in run("cat /tmp/input-hotplug-monitor.jsonl").splitlines()]

    def device_events(devices, source, action, offset=0):
        matching = []
        for record in records()[offset:]:
            if record.get("source") != source:
                continue
            if source == "raw":
                properties = record["properties"]
                node = "/dev/" + properties.get("DEVNAME", "")
                event_action = properties.get("ACTION")
            else:
                node, event_action = record.get("node"), record.get("action")
            if node in devices and event_action == action:
                matching.append(record)
        return matching

    hook = b'''#!/bin/sh
case "$DEVNAME" in input/event*) ;; *) exit 0 ;; esac
marker="/tmp/input-hotplug-finished.${DEVNAME##*/}"
case "$ACTION" in
add) rm -f "$marker"; sleep 1; : > "$marker" ;;
remove) rm -f "$marker" ;;
esac
'''
    qmp = QMP(args.qmp)
    added = set()
    probe_started = False
    hook_installed = False
    report = {"pid1": run("cat /proc/1/comm").strip(), "cycles": []}
    try:
        run("test ! -e /etc/hotplug.d/input/99-hotplug-test; test ! -e /tmp/input-hotplug-monitor.pid")
        run("mkdir -p /etc/hotplug.d/input")
        upload("/etc/hotplug.d/input/99-hotplug-test", hook)
        hook_installed = True
        probe = Path(__file__).with_name("input-hotplug-monitor.py").read_bytes()
        upload("/tmp/input-hotplug-monitor.py", probe)
        run("nohup python3 -u /tmp/input-hotplug-monitor.py > /tmp/input-hotplug-monitor.jsonl 2> /tmp/input-hotplug-monitor.err < /dev/null & echo $! > /tmp/input-hotplug-monitor.pid")
        probe_started = True
        wait(lambda: any(record.get("ready") for record in records()))
        run("nohup stdbuf -oL libinput debug-events > /tmp/input-hotplug-libinput.log 2>&1 < /dev/null & echo $! > /tmp/input-hotplug-libinput.pid")
        desktop_pid = None
        if not args.no_desktop:
            run("! id hotplugcheck >/dev/null 2>&1; useradd -m -U -s /bin/ash hotplugcheck")
            # Send the disposable password over stdin; do not store or log it.
            run("chpasswd", ("hotplugcheck:" + secrets.token_urlsafe(24) + "\n").encode())
            run("desktop-setup hotplugcheck", timeout=60)
            desktop_pid = wait(lambda: run("pidof weston || true").strip())
            run("uid=$(id -u hotplugcheck); runtime=/run/user/$uid; [ -d \"$runtime\" ] || runtime=/tmp/run/desktop-$uid; "
                "display=$(find \"$runtime\" -maxdepth 1 -type s -name 'wayland-*' | head -n 1); test -n \"$display\"; "
                "su -s /bin/ash hotplugcheck -c \"XDG_RUNTIME_DIR=$runtime WAYLAND_DISPLAY=${display##*/} "
                "nohup stdbuf -oL weston-eventdemo --width=640 --height=480 --log-motion --log-button --log-axis --log-key "
                "> /tmp/input-hotplug-wayland.log 2>&1 < /dev/null &\"")
            time.sleep(2)

        group = int(run("awk -F: '$1 == \"input\" { print $3 }' /etc/group").strip())
        for cycle in range(2):
            offset = len(records())
            for driver, identifier in [("usb-tablet", "hotplug-tablet"), ("usb-mouse", "hotplug-mouse"), ("usb-kbd", "hotplug-keyboard")]:
                qmp.command("device_add", {"driver": driver, "id": identifier, "bus": "hotplug-usb.0"})
                added.add(identifier)
            def added_devices():
                nodes = [
                    "/dev/" + r["properties"]["DEVNAME"] for r in records()[offset:]
                    if r.get("source") == "raw" and r["properties"].get("ACTION") == "add"
                    and r["properties"].get("DEVNAME", "").startswith("input/event")
                ]
                return nodes if len(nodes) == 3 else []

            devices = wait(added_devices)
            wait(lambda: len(device_events(devices, "libudev", "add", offset)) == 3)
            raw = device_events(devices, "raw", "add", offset)
            for record in raw:
                assert record["helper_finished"], record
                node = record["node"]
                assert node and node["character"] and node["uid"] == 0 and node["gid"] == group, record
                # Native systemd's devtmpfs may precreate nodes at 0600.
                # seatd opens them as root; bare procd creates them at 0660.
                assert node["mode"] in (0o600, 0o660), record
            if desktop_pid:
                baseline = run("cat /tmp/input-hotplug-wayland.log")
                events = [
                    {"type": "abs", "data": {"axis": "x", "value": 16000}},
                    {"type": "abs", "data": {"axis": "y", "value": 16000}},
                    {"type": "rel", "data": {"axis": "x", "value": 5}},
                    {"type": "btn", "data": {"button": "left", "down": True}},
                    {"type": "btn", "data": {"button": "left", "down": False}},
                    {"type": "btn", "data": {"button": "wheel-up", "down": True}},
                    {"type": "btn", "data": {"button": "wheel-up", "down": False}},
                    {"type": "key", "data": {"key": {"type": "qcode", "data": "a"}, "down": True}},
                    {"type": "key", "data": {"key": {"type": "qcode", "data": "a"}, "down": False}},
                ]
                # Separate HID reports so press/release cannot coalesce and
                # allow Wayland to establish pointer focus before clicking.
                qmp.command("input-send-event", {"events": events[:2]})
                time.sleep(0.3)
                for event in events[2:]:
                    qmp.command("input-send-event", {"events": [event]})
                    time.sleep(0.15)

                def delivered_input():
                    output = run("cat /tmp/input-hotplug-wayland.log")[len(baseline):]
                    return all(word in output for word in ["motion time:", "button time:", "axis", "key key:"])

                wait(delivered_input)
                assert run("pidof weston").strip() == desktop_pid, "Weston restarted"
            for identifier in list(added):
                qmp.command("device_del", {"id": identifier})
                added.remove(identifier)
            wait(lambda: len(device_events(devices, "raw", "remove", offset)) == 3)
            wait(lambda: len(device_events(devices, "libudev", "remove", offset)) == 3)
            report["cycles"].append({"devices": devices, "permissions_ready": True, "node_modes": [oct(r["node"]["mode"]) for r in raw], "helpers_completed": True, "libudev_add_remove": True, "wayland_input": bool(desktop_pid)})

        upload("/tmp/input-hotplug-spoof.py", b'''import socket
s=socket.socket(socket.AF_NETLINK, socket.SOCK_DGRAM, 15)
s.sendto(b"add@/devices/virtual/input/hotplug-spoof\\0ACTION=add\\0DEVPATH=/devices/virtual/input/hotplug-spoof\\0SUBSYSTEM=input\\0DEVNAME=input/hotplug-spoof\\0MAJOR=13\\0MINOR=0\\0", (0, 1))
''')
        run("python3 /tmp/input-hotplug-spoof.py")
        time.sleep(2)
        run("test ! -e /dev/input/hotplug-spoof")
        assert not any("hotplug-spoof" in json.dumps(record) for record in records())
        report["userspace_sender_rejected"] = True
        time.sleep(2)
        raw = [r for r in records() if r.get("source") == "raw"]
        keys = [(r["properties"].get("ACTION"), r["properties"].get("DEVPATH"), r["properties"].get("SEQNUM")) for r in raw]
        assert len(keys) == len(set(keys)), "Duplicate rebroadcasts or feedback loop"
        report["no_duplicate_rebroadcasts"] = True
        report["weston_pid_unchanged"] = bool(desktop_pid)
        for name in ["monitor.jsonl", "monitor.err", "libinput.log"] + (["wayland.log"] if desktop_pid else []):
            (args.output / name).write_text(run("cat /tmp/input-hotplug-" + name))
        (args.output / "results.json").write_text(json.dumps(report, indent=2) + "\n")
        print(json.dumps(report, indent=2))
    finally:
        for identifier in added:
            qmp.command("device_del", {"id": identifier})
        qmp.close()
        if probe_started:
            run("kill $(cat /tmp/input-hotplug-monitor.pid) $(cat /tmp/input-hotplug-libinput.pid 2>/dev/null) 2>/dev/null || true; rm -f /tmp/input-hotplug-monitor.pid /tmp/input-hotplug-libinput.pid")
        if hook_installed:
            run("rm -f /etc/hotplug.d/input/99-hotplug-test")


if __name__ == "__main__":
    main()
