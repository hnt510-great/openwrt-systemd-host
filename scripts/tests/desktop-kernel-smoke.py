#!/usr/bin/env python3
"""Run as root inside a disposable VM booted from the desktop firmware image."""

import fcntl
import json
import os
import selectors
import struct
import subprocess
import time
import uuid
from pathlib import Path


def check_kvm():
    fd = os.open("/dev/kvm", os.O_RDWR | os.O_CLOEXEC)
    try:
        assert fcntl.ioctl(fd, 0xAE00, 0) == 12, "Unexpected KVM API"
        for name, cap in [("Hyper-V", 44), ("Hyper-V spinlocks", 46),
                          ("Hyper-V time", 96)]:
            assert fcntl.ioctl(fd, 0xAE03, cap) > 0, f"Missing {name} capability"
        buf = bytearray(4 + 4096 * 4)
        struct.pack_into("I", buf, 0, 4096)
        fcntl.ioctl(fd, 0xC004AE02, buf, True)
        count = struct.unpack_from("I", buf)[0]
        msrs = struct.unpack_from(f"{count}I", buf, 4)
        assert 0x40000021 in msrs, "Missing Hyper-V reference TSC MSR"
    finally:
        os.close(fd)


def check_modules():
    modules = [
        "configs", "8021q", "8250", "vhost_net", "vhost_vsock", "vfio_pci",
        "hid_multitouch", "uinput", "joydev", "uhid",
        "snd_hda_intel", "snd_hda_codec_alc269", "snd_hda_codec_intelhdmi",
        "snd_usb_audio", "btusb", "uvcvideo", "uas", "loop", "nbd",
        "dm_crypt", "sg", "sr_mod", "bfq", "btrfs", "exfat", "ntfs3",
        "udf", "cifs", "nfsv4", "9p", "cdc_acm", "usblp", "ch341",
        "cp210x", "ftdi_sio", "pl2303", "ax88179_178a", "cdc_ether",
        "cdc_ncm", "rndis_host", "drivetemp", "iwlwifi",
    ]
    for module in modules:
        subprocess.run(["modprobe", module], check=True)
    # Exercise single-file config handling as well as short built-in names:
    # OpenWrt's kmod basename compatibility patch formerly used freed memory.
    config = Path("/tmp/desktop-kmod-smoke.conf")
    config.write_text("alias desktop_smoke_touch hid_multitouch\n")
    try:
        result = subprocess.run(["modprobe", "-C", str(config), "--show-depends",
                                 "desktop_smoke_touch"], check=True,
                                capture_output=True, text=True)
        assert "hid-multitouch.ko" in result.stdout, result.stdout
    finally:
        config.unlink()
    for path in ["/proc/config.gz", "/dev/vhost-net", "/dev/vhost-vsock",
                 "/proc/pressure/cpu", "/proc/pressure/memory",
                 "/proc/pressure/io", "/proc/self/smaps"]:
        assert os.path.exists(path), f"Missing {path}"
    with open("/sys/kernel/mm/transparent_hugepage/enabled") as stream:
        assert "[madvise]" in stream.read(), "Unexpected THP default"
    return modules


def check_hyperv_start():
    # No guest disks or network devices are opened. This exercises the exact
    # CPU flags that triggered win2k25's KVM_SET_MSRS assertion before boot.
    command = [
        "qemu-system-x86_64", "-name", "desktop-hyperv-smoke", "-nodefaults",
        "-machine", "q35", "-accel", "kvm", "-cpu",
        "host,hv-time=on,hv-spinlocks=0x1fff", "-m", "128", "-smp", "1",
        "-display", "none", "-serial", "none", "-monitor", "none",
        "-qmp", "stdio", "-S",
    ]
    process = subprocess.Popen(command, stdin=subprocess.PIPE,
                               stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    selector = selectors.DefaultSelector()
    selector.register(process.stdout, selectors.EVENT_READ)
    pending = bytearray()

    def receive(predicate):
        deadline = time.monotonic() + 15
        while time.monotonic() < deadline:
            while b"\n" in pending:
                line, _, rest = pending.partition(b"\n")
                pending[:] = rest
                message = json.loads(line)
                if predicate(message):
                    return message
            if selector.select(max(0, deadline - time.monotonic())):
                data = os.read(process.stdout.fileno(), 65536)
                if not data:
                    raise RuntimeError("QEMU exited: " +
                                       process.stderr.read().decode())
                pending.extend(data)
        raise TimeoutError("QMP response timed out")

    def execute(name):
        process.stdin.write((json.dumps({"execute": name, "id": name}) +
                             "\n").encode())
        process.stdin.flush()
        message = receive(lambda msg: msg.get("id") == name)
        assert "error" not in message, message
        return message.get("return")

    try:
        receive(lambda msg: "QMP" in msg)
        execute("qmp_capabilities")
        execute("cont")
        # Allow initialization and several vCPU entries before checking state.
        time.sleep(1)
        status = execute("query-status")
        assert status["running"], status
        execute("stop")
        execute("quit")
        process.wait(timeout=10)
        assert process.returncode == 0, process.stderr.read().decode()
    finally:
        selector.close()
        if process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()


def check_libvirt_start():
    import libvirt

    name = "desktop-hyperv-smoke-" + uuid.uuid4().hex[:12]
    xml = f"""<domain type='kvm'>
      <name>{name}</name>
      <memory unit='MiB'>128</memory><vcpu>1</vcpu>
      <os><type arch='x86_64' machine='q35'>hvm</type></os>
      <features><acpi/><apic/>
        <hyperv><spinlocks state='on' retries='8191'/></hyperv>
      </features>
      <cpu mode='host-passthrough'/>
      <clock offset='localtime'><timer name='hypervclock' present='yes'/></clock>
      <devices><emulator>/usr/bin/qemu-system-x86_64</emulator></devices>
    </domain>"""
    connection = libvirt.open("qemu:///system")
    domain = None
    try:
        domain = connection.createXML(xml, 0)
        time.sleep(1)
        assert domain.isActive() and domain.state()[0] == libvirt.VIR_DOMAIN_RUNNING
    finally:
        if domain is not None and domain.isActive():
            domain.destroy()
        connection.close()


if __name__ == "__main__":
    assert os.geteuid() == 0, "Run as root in the disposable firmware VM"
    assert open("/proc/1/comm").read().strip() == "systemd"
    check_kvm()
    modules = check_modules()
    check_hyperv_start()
    check_libvirt_start()
    print(json.dumps({"result": "desktop-kernel-smoke-passed",
                      "hyperv_reference_tsc": True,
                      "qemu_hyperv_start": True,
                      "libvirt_hyperv_start": True,
                      "modules_loaded": modules}, indent=2))
