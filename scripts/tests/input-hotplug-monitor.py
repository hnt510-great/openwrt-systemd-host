#!/usr/bin/env python3
"""Observe raw rebroadcasts and the real libudev API in a disposable guest."""

import ctypes
import json
import os
from pathlib import Path
import select
import socket
import stat
import time


def main():
    lib = ctypes.CDLL("libudev.so.1")
    pointer = ctypes.c_void_p
    signatures = {
        "udev_new": (pointer, []),
        "udev_monitor_new_from_netlink": (pointer, [pointer, ctypes.c_char_p]),
        "udev_monitor_filter_add_match_subsystem_devtype": (
            ctypes.c_int, [pointer, ctypes.c_char_p, ctypes.c_char_p]
        ),
        "udev_monitor_enable_receiving": (ctypes.c_int, [pointer]),
        "udev_monitor_get_fd": (ctypes.c_int, [pointer]),
        "udev_monitor_receive_device": (pointer, [pointer]),
        "udev_device_get_action": (ctypes.c_char_p, [pointer]),
        "udev_device_get_devnode": (ctypes.c_char_p, [pointer]),
        "udev_device_get_property_value": (ctypes.c_char_p, [pointer, ctypes.c_char_p]),
        "udev_device_unref": (pointer, [pointer]),
    }
    for name, (result, arguments) in signatures.items():
        function = getattr(lib, name)
        function.restype = result
        function.argtypes = arguments

    udev = lib.udev_new()
    monitor = lib.udev_monitor_new_from_netlink(udev, b"udev")
    assert udev and monitor
    assert lib.udev_monitor_filter_add_match_subsystem_devtype(monitor, b"input", None) == 0
    assert lib.udev_monitor_enable_receiving(monitor) == 0
    fd = lib.udev_monitor_get_fd(monitor)
    raw = socket.socket(socket.AF_NETLINK, socket.SOCK_DGRAM, 15)
    raw.bind((0, 4))
    print(json.dumps({"ready": True}), flush=True)

    while True:
        for source in select.select([raw, fd], [], [])[0]:
            if source == raw:
                payload, sender = raw.recvfrom(8192)
                properties = {}
                for item in payload.split(b"\0"):
                    if b"=" in item:
                        key, value = item.split(b"=", 1)
                        properties[key.decode()] = value.decode(errors="replace")
                record = {"source": "raw", "sender": sender, "properties": properties}
                devname = properties.get("DEVNAME", "")
                if devname.startswith("input/event") and properties.get("ACTION") == "add":
                    node = Path("/dev") / devname
                    try:
                        info = node.stat()
                        record["node"] = {
                            "character": stat.S_ISCHR(info.st_mode),
                            "uid": info.st_uid,
                            "gid": info.st_gid,
                            "mode": stat.S_IMODE(info.st_mode),
                        }
                    except FileNotFoundError:
                        record["node"] = None
                    record["helper_finished"] = Path(
                        "/tmp/input-hotplug-finished." + node.name
                    ).exists()
            else:
                device = lib.udev_monitor_receive_device(monitor)
                if not device:
                    continue

                def decode(value):
                    return value.decode(errors="replace") if value else None

                record = {
                    "source": "libudev",
                    "action": decode(lib.udev_device_get_action(device)),
                    "node": decode(lib.udev_device_get_devnode(device)),
                    "mouse": decode(lib.udev_device_get_property_value(device, b"ID_INPUT_MOUSE")),
                    "keyboard": decode(lib.udev_device_get_property_value(device, b"ID_INPUT_KEYBOARD")),
                }
                lib.udev_device_unref(device)
            record["time"] = time.monotonic()
            print(json.dumps(record), flush=True)


if __name__ == "__main__":
    assert os.getuid() == 0, "Run only as root inside a disposable test guest"
    main()
