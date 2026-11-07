"""Small whiptail screens with back navigation and an editable new layout."""
import fcntl
import os
import pty
import select
import struct
import termios
import time
import tty
from pathlib import Path
import subprocess
import tempfile

import core
import apply


class Back(Exception):
    pass


def run_dialog(args):
    """Relay a terminal to newt, adding Escape-to-back without feed patches.

    Stock whiptail forms bind F12 but do not bind Escape. Keep CSI/SS3 cursor
    sequences intact, and treat an isolated Escape as cancellation.
    """
    master, slave = pty.openpty()
    saved = termios.tcgetattr(0)
    size = fcntl.ioctl(0, termios.TIOCGWINSZ, bytes(8))
    rows, cols, _, _ = struct.unpack('HHHH', size)
    fcntl.ioctl(slave, termios.TIOCSWINSZ, struct.pack('HHHH', rows or 25, cols or 80, 0, 0))
    def child_terminal():
        os.setsid()
        fcntl.ioctl(slave, termios.TIOCSCTTY, 0)
    process = subprocess.Popen(args, stdin=slave, stdout=slave, stderr=subprocess.PIPE,
                               preexec_fn=child_terminal)
    os.close(slave)
    result = bytearray()
    pending_escape = None
    cancelled = False
    try:
        tty.setraw(0)
        while process.poll() is None:
            ready, _, _ = select.select([0, master, process.stderr], [], [], .1)
            for fd in ready:
                if fd == master:
                    try:
                        data = os.read(master, 65536)
                    except OSError:
                        data = b''
                    if data:
                        os.write(1, data)
                elif fd == process.stderr:
                    result.extend(os.read(process.stderr.fileno(), 65536))
                else:
                    data = os.read(0, 4096)
                    if not data:
                        cancelled = True
                        break
                    forward = bytearray()
                    for byte in data:
                        if pending_escape is not None:
                            if byte in (ord('['), ord('O')):
                                forward.extend((27, byte))
                                pending_escape = None
                            else:
                                cancelled = True
                                break
                        elif byte == 27:
                            pending_escape = time.monotonic()
                        else:
                            forward.append(byte)
                    if forward:
                        os.write(master, forward)
            if cancelled or (pending_escape is not None and time.monotonic() - pending_escape >= .15):
                cancelled = True
                break
        if cancelled:
            process.terminate()
        process.wait(timeout=2)
        result.extend(process.stderr.read())
        # Deliver the terminal restoration bytes before starting another form.
        while select.select([master], [], [], 0)[0]:
            try:
                data = os.read(master, 65536)
            except OSError:
                break
            if not data:
                break
            os.write(1, data)
        return subprocess.CompletedProcess(args, 255 if cancelled else process.returncode,
                                           stderr=result.decode(errors='replace'))
    finally:
        if process.poll() is None:
            process.kill(); process.wait()
        process.stderr.close()
        os.close(master)
        termios.tcsetattr(0, termios.TCSADRAIN, saved)


def dialog(kind, text, items=(), default=None):
    args = ['whiptail', '--title', 'OpenWrt installer', '--backtitle', 'OpenWrt — whole disk installation']
    if default is not None and kind in ('inputbox', 'passwordbox'):
        tail = [str(default)]
    else:
        tail = list(items)
    if default is not None and kind == 'menu':
        args += ['--default-item', str(default)]
    if kind == 'yesno':
        args += ['--defaultno'] if not default else []
    if kind in ('menu', 'checklist', 'radiolist'):
        dimensions = ['22', '78', '13']
    else:
        dimensions = ['22' if kind == 'textbox' else '12', '78']
    p = run_dialog(args + ['--' + kind, text] + dimensions + tail)
    if kind == 'yesno' and p.returncode == 1:
        return False
    if p.returncode:
        raise Back()
    return True if kind == 'yesno' else p.stderr


def menu(text, items, default=None):
    return dialog('menu', text, [str(v) for pair in items for v in pair], default)


def yes(text, default=True):
    return dialog('yesno', text, default=default)


def password(label):
    while True:
        first = dialog('passwordbox', label)
        second = dialog('passwordbox', 'Repeat password')
        if first and first == second:
            return apply.run('openssl', 'passwd', '-6', '-stdin', input=first + '\n')
        dialog('msgbox', 'Passwords must match and cannot be empty.')


def fs_choice(extra=False):
    choices = list(core.FILESYSTEMS) + (['unformatted'] if extra else [])
    return menu('Filesystem', [(x, x) for x in choices])


def partitioning(a, size, payload):
    mode = menu('Create a fresh GPT on the whole disk', [('guided', 'Guided — use entire disk (recommended)'), ('manual', 'Manual — edit the new layout')])
    if mode == 'guided':
        a['partitions'] = core.guided(payload, fs_choice())
    while True:
        plan = core.layout(a['partitions'], size, payload)
        preview = '\n'.join(f"p{p['number']}: {p['role']} {p['size_mib']} MiB {p.get('fs', '')}" for p in plan['partitions'])
        if mode == 'guided':
            dialog('msgbox', preview)
            return
        selected = menu(preview, [(str(i), f"Edit p{i+1}") for i in range(len(a['partitions']))] + [('add', 'Free space — create data partition'), ('done', 'Done')])
        if selected == 'done':
            return
        old = [dict(p) for p in a['partitions']]
        try:
            if selected == 'add':
                size_text = dialog('inputbox', 'Data size in MiB (leave blank for remaining space)')
                a['partitions'].append({'role': 'data', 'size_mib': int(size_text) if size_text else None, 'fs': fs_choice(True)})
            else:
                i = int(selected)
                action = menu('Edit partition', [('size', 'Change size'), *([('fs', 'Change filesystem')] if i >= 2 else []), *([('delete', 'Delete partition')] if i >= 3 else [])])
                if action == 'delete':
                    a['partitions'].pop(i)
                elif action == 'fs':
                    a['partitions'][i]['fs'] = fs_choice(i >= 3)
                else:
                    value = dialog('inputbox', 'Size in MiB (blank = remaining space)', default=a['partitions'][i]['size_mib'] or '')
                    a['partitions'][i]['size_mib'] = int(value) if value else None
            core.layout(a['partitions'], size, payload)
        except Back:
            a['partitions'] = old
        except ValueError as exc:
            a['partitions'] = old
            dialog('msgbox', str(exc))


def ports(a):
    while True:
        interfaces = core.nics()
        for nic in interfaces:
            apply.run('ip', 'link', 'set', nic['name'], 'up')
        interfaces = core.nics()
        items = [(n['name'], f"{n['mac']} {n['driver']} link={n['carrier']}") for n in interfaces]
        wan = menu('Choose WAN port', [('none', 'None — LAN only'), *items, ('refresh', 'Refresh link status')], default='eth1' if any(n['name'] == 'eth1' for n in interfaces) else 'none')
        if wan == 'refresh':
            continue
        a['network']['wan_port'] = None if wan == 'none' else wan
        options = []
        for name, label in items:
            if name != wan:
                options.extend([name, label, 'ON'])
        import shlex
        a['network']['lan_ports'] = shlex.split(dialog('checklist', 'Choose LAN ports', options))
        return


def lan(a):
    l = a['network']['lan']
    while True:
        key = menu('LAN settings', [(k, str(v)) for k, v in l.items()] + [('continue', 'Continue')])
        if key == 'continue':
            return
        if key == 'dhcp':
            l[key] = yes('Enable DHCP server?')
        else:
            v = dialog('inputbox', key, default=l[key])
            l[key] = int(v) if key in ('start', 'limit') else v


def wan(a):
    n = a['network']
    proto = menu('WAN connection', [(p, p.upper()) for p in ('dhcp', 'pppoe', 'static', 'none')]) if n.get('wan_port') else 'none'
    w = {'proto': proto}
    if proto == 'pppoe':
        w['username'] = dialog('inputbox', 'PPPoE username')
        w['password'] = dialog('passwordbox', 'PPPoE password')
    if proto == 'static':
        for key in ('ipaddr', 'netmask', 'gateway'):
            w[key] = dialog('inputbox', 'WAN ' + key)
        w['dns'] = dialog('inputbox', 'DNS addresses separated by spaces').split()
    n['wan'] = w; n['ipv6'] = yes('Enable IPv6?')


def firewall(a):
    import shlex
    selected = shlex.split(dialog('checklist', 'LAN: accept input/output/forward\nWAN: reject input/forward, accept output',
                                 ['masq', 'WAN NAT masquerade', 'ON', 'fullcone', 'Full-cone NAT (requires masquerade)', 'OFF', 'lan_to_wan', 'LAN to WAN forwarding', 'ON']))
    a['firewall'] = {key: key in selected for key in ('masq', 'fullcone', 'lan_to_wan')}


def accounts(a):
    root = password('Root password (required)')
    name = dialog('inputbox', 'Regular username (optional)')
    user = None
    if name:
        user = {'name': name, 'password_hash': password('User password'), 'gnome_autostart': yes('Start GNOME automatically at boot?')}
    a['accounts'] = {'root_password_hash': root, 'user': user}


def show_summary(a, plan):
    with tempfile.NamedTemporaryFile(mode='w') as f:
        f.write(core.display_summary(a, plan)); f.flush()
        dialog('textbox', f.name)


def progress_install(a, manifest, payload):
    gauge = subprocess.Popen(['whiptail', '--title', 'Installing OpenWrt', '--gauge', 'Preparing', '10', '76', '0'], stdin=subprocess.PIPE, text=True)
    try:
        def progress(n, text):
            gauge.stdin.write(f'XXX\n{n}\n{text}\nXXX\n'); gauge.stdin.flush()
        apply.install(a, manifest, payload, progress)
    finally:
        gauge.stdin.close(); gauge.wait()


def main(manifest, payload):
    a = {'partitions': core.guided(manifest['squashfs_size']),
         'network': {'wan_port': 'eth1', 'lan_ports': ['eth0'],
                     'lan': {'ipaddr': '192.168.1.1', 'netmask': '255.255.255.0', 'dhcp': True, 'start': 100, 'limit': 150},
                     'wan': {'proto': 'dhcp'}, 'ipv6': True},
         'firewall': {'masq': True, 'fullcone': False, 'lan_to_wan': True}}
    step = 0; disk_size = 0
    while True:
        try:
            if step == 0:
                choice = menu('Welcome. This installer erases the entire selected disk.', [('install', 'Install OpenWrt'), ('shell', 'Open shell'), ('reboot', 'Reboot')])
                if choice == 'shell':
                    subprocess.run(['/bin/sh']); continue
                if choice == 'reboot':
                    apply.run('systemctl', 'reboot'); return
            elif step == 1:
                _, _, disks = apply.discover()
                a['disk'] = menu('Target disk (installer USB is hidden)', [(d['path'], f"{int(d['size']) // core.MIB} MiB {d.get('model') or ''}") for d in disks])
                disk_size = int(next(d['size'] for d in disks if d['path'] == a['disk']))
            elif step == 2:
                partitioning(a, disk_size, manifest['squashfs_size'])
            elif step == 3:
                ports(a)
            elif step == 4:
                lan(a)
            elif step == 5:
                wan(a)
            elif step == 6:
                firewall(a)
            elif step == 7:
                accounts(a)
            elif step == 8:
                validated = apply.install(a, manifest, payload, dry_run=True)
                show_summary(a, validated['layout'])
                if not yes('ALL DATA ON ' + a['disk'] + ' WILL BE ERASED. Install?', False):
                    continue
                try:
                    progress_install(a, manifest, payload)
                except Exception as exc:
                    with open('/tmp/openwrt-installer.log', 'a') as log:
                        log.write(str(exc) + '\n')
                    dialog('msgbox', str(exc))
                    if menu('Installation failed', [('summary', 'Back to summary'), ('shell', 'Open shell')]) == 'shell':
                        subprocess.run(['/bin/sh'])
                    continue
                dialog('msgbox', 'Installation complete. Remove the USB stick and press Enter to reboot.')
                apply.run('systemctl', 'reboot'); return
            step += 1
        except Back:
            step = max(0, step - 1)
        except (ValueError, KeyError, RuntimeError) as exc:
            dialog('msgbox', str(exc)); step = max(1, step - 1)
