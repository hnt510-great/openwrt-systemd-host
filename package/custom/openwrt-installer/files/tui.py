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


def components(a, catalog):
    import shlex
    while True:
        current = set(a.get('components') or [])
        options = []
        for comp in catalog['components']:
            label = comp['label']
            if comp.get('depends'):
                label += ' (requires: ' + ', '.join(comp['depends']) + ')'
            options.extend([comp['id'], label, 'ON' if comp['id'] in current else 'OFF'])
        selected = shlex.split(dialog(
            'checklist',
            'Select optional components to install offline (base router and ops tools are always installed).',
            options,
        ))
        # Preserve the user's exact selection even if validation fails.
        a['components'] = selected
        try:
            a['components'] = core.validate_components(selected, catalog)
            return
        except ValueError as exc:
            dialog('msgbox', str(exc))


def partitioning(a, size, payload, min_overlay=core.MIN_OVERLAY_MIB):
    mode = menu('Create a fresh GPT on the whole disk', [('guided', 'Guided — use entire disk (recommended)'), ('manual', 'Manual — edit the new layout')])
    if mode == 'guided':
        a['partitions'] = core.guided(payload, fs_choice())
    while True:
        plan = core.layout(a['partitions'], size, payload, min_overlay=min_overlay)
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
            core.layout(a['partitions'], size, payload, min_overlay=min_overlay)
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
        wan = menu('Choose WAN port', [('none', 'None — LAN only'), *items, ('refresh', 'Refresh link status')], default=a['network'].get('wan_port') or 'none')
        if wan == 'refresh':
            continue
        a['network']['wan_port'] = None if wan == 'none' else wan
        options = []
        for name, label in items:
            if name != wan:
                options.extend([name, label, 'ON' if name in a['network']['lan_ports'] else 'OFF'])
        import shlex
        a['network']['lan_ports'] = shlex.split(dialog('checklist', 'Choose LAN ports', options))
        return


def lan(a):
    l = a['network']['lan']
    while True:
        key = menu('LAN settings', [(k, str(v)) for k, v in l.items()] + [('continue', 'Continue')])
        if key == 'continue':
            try:
                core.validate_lan(l)
            except ValueError as exc:
                dialog('msgbox', str(exc)); continue
            return
        if key == 'dhcp':
            l[key] = yes('Enable DHCP server?', l[key])
        else:
            v = dialog('inputbox', key, default=l[key])
            try:
                l[key] = int(v) if key in ('start', 'limit') else v
            except ValueError:
                dialog('msgbox', 'Enter a whole number.'); continue


def wan(a):
    n = a['network']
    while True:
        proto = menu('WAN connection', [(p, p.upper()) for p in ('dhcp', 'pppoe', 'static', 'none')],
                     default=n['wan']['proto']) if n.get('wan_port') else 'none'
        old = n['wan']
        w = {'proto': proto}
        if proto == 'pppoe':
            w['username'] = dialog('inputbox', 'PPPoE username', default=old.get('username', ''))
            w['password'] = old.get('password') or dialog('passwordbox', 'PPPoE password')
        if proto == 'static':
            for key in ('ipaddr', 'netmask', 'gateway'):
                w[key] = dialog('inputbox', 'WAN ' + key, default=old.get(key, ''))
            w['dns'] = dialog('inputbox', 'DNS addresses separated by spaces', default=' '.join(old.get('dns', []))).split()
        n['wan'] = w
        try:
            core.validate_wan(n)
        except ValueError as exc:
            dialog('msgbox', str(exc)); continue
        n['ipv6'] = yes('Enable IPv6?', n['ipv6'])
        return


def firewall(a):
    import shlex
    selected = shlex.split(dialog('checklist', 'LAN: accept input/output/forward\nWAN: reject input/forward, accept output',
                                 [value for key, label in [('masq', 'WAN NAT masquerade'), ('fullcone', 'Full-cone NAT (requires masquerade)'), ('lan_to_wan', 'LAN to WAN forwarding')] for value in (key, label, 'ON' if a['firewall'][key] else 'OFF')]))
    a['firewall'] = {key: key in selected for key in ('masq', 'fullcone', 'lan_to_wan')}


def accounts(a, has_gnome=True):
    root = password('Root password (required)')
    name = dialog('inputbox', 'Regular username (optional)')
    user = None
    if name:
        autostart = yes('Start GNOME automatically at boot?') if has_gnome else False
        user = {'name': name, 'password_hash': password('User password'), 'gnome_autostart': autostart}
    a['accounts'] = {'root_password_hash': root, 'user': user}


def show_summary(a, plan, disk=None, component_plan=None):
    with tempfile.NamedTemporaryFile(mode='w') as f:
        f.write(core.display_summary(a, plan, component_plan=component_plan))
        if disk:
            f.write('Disk: ' + str(disk.get('model') or 'unknown model') + '  ' + str(int(disk['size']) // core.MIB) + ' MiB  serial: ' + str(disk.get('serial') or 'unavailable') + '\n')
        f.flush()
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
    catalog = apply.load_components_catalog(manifest, payload)
    a = {'partitions': core.guided(manifest['squashfs_size']),
         'network': {'wan_port': 'eth1', 'lan_ports': ['eth0'],
                     'lan': {'ipaddr': '192.168.1.1', 'netmask': '255.255.255.0', 'dhcp': True, 'start': 100, 'limit': 150},
                     'wan': {'proto': 'dhcp'}, 'ipv6': True},
         'firewall': {'masq': True, 'fullcone': False, 'lan_to_wan': True}}
    if catalog is not None:
        a['components'] = core.default_components(catalog)
    step = 0; disk_size = 0; min_overlay = core.MIN_OVERLAY_MIB
    steps = ['welcome', 'disk', *(['components'] if catalog is not None else []),
             'partitioning', 'ports', 'lan', 'wan', 'firewall', 'accounts', 'summary']
    while True:
        try:
            current = steps[step]
            if current == 'welcome':
                choice = menu('Welcome. This installer erases the entire selected disk.', [('install', 'Install OpenWrt'), ('shell', 'Open shell'), ('reboot', 'Reboot')])
                if choice == 'shell':
                    subprocess.run(['/bin/sh']); continue
                if choice == 'reboot':
                    apply.run('systemctl', 'reboot'); return
            elif current == 'disk':
                _, _, disks = apply.discover()
                a['disk'] = menu('Target disk (installer USB is hidden)', [(d['path'], f"{int(d['size']) // core.MIB} MiB {d.get('model') or ''}") for d in disks])
                disk_size = int(next(d['size'] for d in disks if d['path'] == a['disk']))
            elif current == 'components':
                components(a, catalog)
                plan_preview = apply.preflight_components(a['components'], catalog, payload)
                min_overlay = plan_preview['min_overlay_mib'] if plan_preview else core.MIN_OVERLAY_MIB
            elif current == 'partitioning':
                partitioning(a, disk_size, manifest['squashfs_size'], min_overlay=min_overlay)
            elif current == 'ports':
                ports(a)
            elif current == 'lan':
                lan(a)
            elif current == 'wan':
                wan(a)
            elif current == 'firewall':
                firewall(a)
            elif current == 'accounts':
                has_gnome = True if catalog is None else ('gnome' in (a.get('components') or []))
                accounts(a, has_gnome=has_gnome)
            elif current == 'summary':
                validated = apply.install(a, manifest, payload, dry_run=True)
                show_summary(a, validated['layout'], validated['disk'], validated.get('components'))
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
                dialog('msgbox', 'Installation complete. LAN: ' + a['network']['lan']['ipaddr'] + '. Remove the installation media and press Enter to reboot.')
                apply.run('systemctl', 'reboot'); return
            step += 1
        except Back:
            step = max(0, step - 1)
        except (ValueError, KeyError, RuntimeError) as exc:
            dialog('msgbox', str(exc))
