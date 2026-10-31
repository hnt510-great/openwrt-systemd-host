#!/usr/bin/python3
"""Read-only feature/default checks inside the built native-systemd firmware."""
import importlib
import os
import stat
import subprocess
import sys
import xml.etree.ElementTree as ET
from unittest.mock import patch

import gi
import libvirt

sys.path.insert(0, '/usr/share/virt-manager')
import virtinst

for name, version in [('SpiceClientGLib', '2.0'), ('SpiceClientGtk', '3.0')]:
    gi.require_version(name, version)
    importlib.import_module('gi.repository.' + name)
    print(name, version, 'imported')

from gi.repository import SpiceClientGLib

assert SpiceClientGLib.Session().get_property('gl-scanout'), \
    'SPICE client was built without EGL; VirtIO 3D consoles cannot display'
print('SPICE client GL scanout is enabled by default')

assert open('/proc/1/comm').read().strip() == 'systemd'
raw = libvirt.open('qemu:///system')
caps = ET.fromstring(raw.getDomainCapabilities(None, 'x86_64', None, 'kvm', 0))
assert caps.find("cpu/mode[@name='host-passthrough']").get('supported') == 'yes'
for kind, value in [('graphics', 'spice'), ('video', 'virtio')]:
    values = {e.text for enum in caps.findall("devices/" + kind + "/enum")
              if enum.get("name") in ("type", "modelType") for e in enum.findall("value")}
    assert value in values, (kind, values)
raw.close()
helptext = subprocess.check_output(['qemu-system-x86_64', '-device', 'help'], text=True)
for name in ['virtio-blk-pci', 'virtio-net-pci', 'virtio-vga', 'virtio-vga-gl']:
    assert 'name "' + name + '"' in helptext, name

conn = virtinst.VirtinstConnection('qemu:///system')
conn.open(None, None)
try:
    guest = virtinst.Guest(conn)
    guest.name = 'virtio-spice-read-only-audit'
    guest.type = 'kvm'
    guest.os.arch = 'x86_64'
    guest.os.os_type = 'hvm'
    guest.memory = 512 * 1024
    guest.vcpus = 1
    guest.set_defaults(None)
    xml = ET.fromstring(guest.get_xml())
    assert xml.find('devices/graphics').get('type') == 'spice'
    assert xml.find('devices/graphics/listen').get('type') == 'none'
    assert xml.find('devices/graphics/gl') is None
    assert xml.find('devices/video/model').get('type') == 'virtio'
    acceleration = xml.find('devices/video/model/acceleration')
    assert acceleration is None or acceleration.get('accel3d') != 'yes'
    assert not xml.findall('devices/sound')
    assert not xml.findall('devices/redirdev')
    print('New defaults: local SPICE, VirtIO video, 3D off, no automatic sound/USB redirection')

    explicit = virtinst.Guest(conn, parsexml="""<domain type='kvm'>
      <name>existing-explicit-audit</name><memory>524288</memory><vcpu>1</vcpu>
      <os><type arch='x86_64'>hvm</type></os>
      <devices><graphics type='vnc' listen='127.0.0.1'/>
      <video><model type='vga'/></video>
      <disk type='file' device='disk'><source file='/srv/libvirt/images/audit.qcow2'/>
      <target dev='sda' bus='sata'/></disk></devices></domain>""")
    explicit.set_defaults(None)
    xml = ET.fromstring(explicit.get_xml())
    assert xml.find('devices/graphics').get('type') == 'vnc'
    assert xml.find('devices/video/model').get('type') == 'vga'
    assert xml.find('devices/disk/target').get('bus') == 'sata'
    print('Explicit VNC/VGA/SATA configuration retained')

    nodes = virtinst.DeviceGraphics.local_rendernodes(conn)
    for node in nodes:
        info = os.stat(node)
        assert stat.S_ISCHR(info.st_mode)
        assert stat.S_IMODE(info.st_mode) == 0o660
        import grp
        assert grp.getgrgid(info.st_gid).gr_name == 'render'
    print('Local render nodes:', nodes)
    with patch.object(conn, 'is_remote', return_value=True), patch('glob.glob') as scan:
        assert virtinst.DeviceGraphics.local_rendernodes(conn) == []
        scan.assert_not_called()
    with patch('glob.glob', return_value=[]):
        assert virtinst.DeviceGraphics.local_rendernodes(conn) == []
finally:
    conn.close()
print('virtio-spice runtime smoke checks passed')
