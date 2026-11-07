"""Installer planning and serialization. No commands or target writes here."""
import copy
import ipaddress
import json
from pathlib import Path
import re
import uuid

MIB = 1024 * 1024
ESP = 'C12A7328-F81F-11D2-BA4B-00A0C93EC93B'
LINUX = '0FC63DAF-8483-4772-8E79-3D69D8477DE4'
BIOS = '21686148-6449-6E6F-744E-656564454649'
FILESYSTEMS = ('ext4', 'btrfs', 'xfs')


def partition(disk, number):
    return disk + ('p' if disk[-1].isdigit() else '') + str(number)


def guided(payload_size, fs='ext4'):
    rom = max(1024, ((payload_size * 5 + 4 * 256 * MIB - 1) // (4 * 256 * MIB)) * 256)
    return [{'role': 'boot', 'size_mib': 512}, {'role': 'rom', 'size_mib': rom},
            {'role': 'overlay', 'fs': fs, 'size_mib': None}]


def layout(parts, disk_size, payload_size, disk_guid=None):
    if [p['role'] for p in parts[:3]] != ['boot', 'rom', 'overlay']:
        raise ValueError('Partitions 1, 2 and 3 must be boot, rom and overlay')
    if len(parts) > 127 or any(p['role'] != 'data' for p in parts[3:]):
        raise ValueError('Only extra data partitions are allowed after overlay')
    if sum(p.get('size_mib') is None for p in parts) > 1:
        raise ValueError('Only one partition may use remaining space')
    # Reserve the final MiB for GPT backup; all regular partitions start on MiB boundaries.
    available = disk_size // MIB - 2
    fixed = 0
    for p in parts:
        size = p.get('size_mib')
        if size is not None:
            if type(size) is not int or size <= 0:
                raise ValueError('Partition sizes must be positive whole MiB')
            fixed += size
    remaining = available - fixed
    base = uuid.UUID(disk_guid).int if disk_guid else uuid.uuid4().int
    base &= ~255
    result, start = [], 2048
    for n, p in enumerate(parts, 1):
        size = remaining if p.get('size_mib') is None else p['size_mib']
        minimum = {1: 64, 2: (payload_size + MIB - 1) // MIB, 3: 2048}.get(n, 1)
        if size < minimum:
            raise ValueError(f'Partition {n} requires at least {minimum} MiB')
        fs = p.get('fs')
        if n >= 3 and fs not in FILESYSTEMS + (('unformatted',) if n > 3 else ()):
            raise ValueError('Unsupported filesystem')
        result.append(dict(p, number=n, start=start, sectors=size * 2048,
                           size_mib=size, uuid=str(uuid.UUID(int=base + n)),
                           type=ESP if n == 1 else LINUX,
                           name=('boot', 'rootfs', 'rootfs_data')[n-1] if n <= 3 else ('data' if n == 4 else f'data{n-3}')))
        start += size * 2048
    if start > (disk_size // MIB - 1) * 2048:
        raise ValueError('Partitions do not fit on the disk')
    return {'disk_guid': str(uuid.UUID(int=base)), 'partitions': result,
            'bios_uuid': str(uuid.UUID(int=base + 128))}


def sfdisk_script(disk, plan):
    lines = ['label: gpt', 'table-length: 128', 'label-id: ' + plan['disk_guid'], 'first-lba: 34', 'unit: sectors']
    for p in plan['partitions']:
        lines.append(f'{p["number"]} : start={p["start"]}, size={p["sectors"]}, type={p["type"]}, uuid={p["uuid"]}, name="{p["name"]}"')
    lines.append(f'128 : start=34, size=2014, type={BIOS}, uuid={plan["bios_uuid"]}, name="bios"')
    return '\n'.join(lines) + '\n'


def validate_answers(answers, existing_users=()):
    a = copy.deepcopy(answers)
    if not re.fullmatch(r'/dev/[a-zA-Z0-9_.-]+', a['disk']):
        raise ValueError('Invalid disk path')
    net = a['network']; lan = net['lan']; wan = net['wan']
    subnet = ipaddress.IPv4Network((lan['ipaddr'], lan['netmask']), strict=False)
    address = ipaddress.IPv4Address(lan['ipaddr'])
    if address in (subnet.network_address, subnet.broadcast_address):
        raise ValueError('LAN address must be a host address')
    if lan['dhcp']:
        start, count = lan['start'], lan['limit']
        if type(start) is not int or type(count) is not int or start < 1 or count < 1 or start + count > subnet.num_addresses - 1:
            raise ValueError('DHCP pool must fit inside LAN subnet')
    ports = net['lan_ports'] + ([net['wan_port']] if net.get('wan_port') else [])
    if not net['lan_ports'] or len(set(ports)) != len(ports) or any(not re.fullmatch(r'[a-zA-Z0-9_.-]{1,15}', p) for p in ports):
        raise ValueError('Choose distinct physical LAN and WAN ports')
    if wan['proto'] not in ('dhcp', 'pppoe', 'static', 'none'):
        raise ValueError('Invalid WAN protocol')
    if not net.get('wan_port') and wan['proto'] != 'none':
        raise ValueError('WAN protocol requires a WAN port')
    if wan['proto'] == 'static':
        ipaddress.IPv4Network((wan['ipaddr'], wan['netmask']), strict=False)
        ipaddress.IPv4Address(wan['gateway'])
        for dns in wan['dns']:
            ipaddress.ip_address(dns)
    if wan['proto'] == 'pppoe':
        for key in ('username', 'password'):
            if not wan.get(key):
                raise ValueError('PPPoE requires username and password')
    accounts = a['accounts']; user = accounts.get('user')
    hashes = [accounts['root_password_hash']]
    if user:
        if not re.fullmatch(r'[a-z_][a-z0-9_-]{0,31}', user['name']) or user['name'] in set(existing_users) | {'root'}:
            raise ValueError('Invalid or existing username')
        if type(user.get('gnome_autostart')) is not bool:
            raise ValueError('GNOME autostart must be a boolean')
        hashes.append(user['password_hash'])
    if any(not re.fullmatch(r'\$6\$(?:rounds=[0-9]+\$)?[./a-zA-Z0-9]{1,16}\$[./a-zA-Z0-9]{86}', h) for h in hashes):
        raise ValueError('Accounts require SHA-512 crypt password hashes')
    for value in (net.get('ipv6'), lan['dhcp'], *[a['firewall'][k] for k in ('masq', 'fullcone', 'lan_to_wan')]):
        if type(value) is not bool:
            raise ValueError('Toggles must be booleans')
    return a


def quote(value):
    value = str(value)
    if any(c in value for c in '\n\r\x00'):
        raise ValueError('UCI values must be single line')
    return "'" + value.replace("'", "'\\''") + "'"


def network_batch(a, ula=None):
    n = a['network']; l = n['lan']; w = n['wan']; ipv6 = n['ipv6']
    lines = []
    def set_(key, value):
        lines.append('set network.' + key + '=' + quote(value))
    set_('loopback', 'interface'); set_('loopback.device', 'lo'); set_('loopback.proto', 'static')
    set_('loopback.ipaddr', '127.0.0.1'); set_('loopback.netmask', '255.0.0.0')
    set_('globals', 'globals')
    if ipv6:
        set_('globals.ula_prefix', ula or ('fd' + uuid.uuid4().hex[:2] + ':' + uuid.uuid4().hex[:4] + ':' + uuid.uuid4().hex[:4] + '::/48'))
    set_('br_lan', 'device'); set_('br_lan.name', 'br-lan'); set_('br_lan.type', 'bridge')
    for port in n['lan_ports']:
        lines.append('add_list network.br_lan.ports=' + quote(port))
    set_('lan', 'interface'); set_('lan.device', 'br-lan'); set_('lan.proto', 'static')
    for k in ('ipaddr', 'netmask'):
        set_('lan.' + k, l[k])
    if ipv6:
        set_('lan.ip6assign', 60)
    if n.get('wan_port') and w['proto'] != 'none':
        set_('wan', 'interface'); set_('wan.device', n['wan_port']); set_('wan.proto', w['proto'])
        for k in ('ipaddr', 'netmask', 'gateway', 'username', 'password'):
            if k in w:
                set_('wan.' + k, w[k])
        for dns in w.get('dns', []):
            lines.append('add_list network.wan.dns=' + quote(dns))
        if w['proto'] == 'pppoe':
            set_('wan.ipv6', 'auto' if ipv6 else '0')
        elif ipv6:
            set_('wan6', 'interface'); set_('wan6.proto', 'dhcpv6'); set_('wan6.device', n['wan_port'])
    return '\n'.join(lines + ['commit network']) + '\n'


def policy_batch(a, firewall_show):
    l = a['network']['lan']; fw = a['firewall']
    # Mark the stock odhcpd global configuration initialized. Its firstboot
    # fallback would otherwise overwrite the chosen LAN IPv6 policy.
    lines = ["set dhcp.odhcpd='odhcpd'", "set dhcp.odhcpd.maindhcp='0'",
             "set dhcp.odhcpd.leasefile='/tmp/odhcpd.leases'",
             "set dhcp.odhcpd.leasetrigger='/usr/sbin/odhcpd-update'",
             "set dhcp.odhcpd.loglevel='4'",
             "set dhcp.odhcpd.piodir='/tmp/odhcpd-piodir'",
             "set dhcp.odhcpd.hostsdir='/tmp/hosts'",
             f"set dhcp.lan.ignore='{int(not l['dhcp'])}'",
             f"set dhcp.lan.start='{l['start']}'", f"set dhcp.lan.limit='{l['limit']}'"]
    if not a['network']['ipv6']:
        lines += ["set dhcp.lan.dhcpv6='disabled'", "set dhcp.lan.ra='disabled'"]
    else:
        lines += ["set dhcp.lan.dhcpv6='server'", "set dhcp.lan.ra='server'",
                  "set dhcp.lan.ra_slaac='1'",
                  "add_list dhcp.lan.ra_flags='managed-config'",
                  "add_list dhcp.lan.ra_flags='other-config'"]
    sections = {}
    for line in firewall_show.splitlines():
        key, sep, value = line.partition('=')
        if sep:
            sections[key] = value.strip("'")
    zones = [k[:-5] for k, v in sections.items() if k.endswith('.name') and v == 'wan' and sections.get(k[:-5]) == 'zone']
    if len(zones) != 1:
        raise ValueError('Stock firewall must contain one WAN zone')
    lines += [f"set {zones[0]}.masq='{int(fw['masq'])}'",
              f"set firewall.@defaults[0].fullcone='{2 if fw['fullcone'] and fw['masq'] else 0}'"]
    for key, val in sections.items():
        if val == 'forwarding' and sections.get(key + '.src') == 'lan' and sections.get(key + '.dest') == 'wan':
            lines.append('delete ' + key)
    if fw['lan_to_wan']:
        lines += ["set firewall.installer_lan_wan='forwarding'", "set firewall.installer_lan_wan.src='lan'", "set firewall.installer_lan_wan.dest='wan'"]
    return '\n'.join(lines + ['commit dhcp', 'commit firewall']) + '\n'


def rewrite_grub(text, old_root, new_uuid, fat_uuid):
    if old_root not in text or 'search -l kernel -s root' not in text:
        raise ValueError('Unexpected target GRUB configuration')
    return text.replace(old_root, 'PARTUUID=' + new_uuid).replace('search -l kernel -s root', 'search --fs-uuid --set=root ' + fat_uuid)


def disks(lsblk, excluded=()):
    return [d for d in lsblk['blockdevices'] if d['type'] == 'disk' and int(d.get('size') or 0) > 0 and not d.get('ro') and d['path'] not in excluded
            and not re.match(r'(loop|sr|zram|mmcblk\d+boot[01])', d['name'])]


def nics(sysfs='/sys/class/net'):
    result = []
    for p in sorted(Path(sysfs).iterdir()):
        if not (p / 'device').exists() or any((p / x).exists() for x in ('wireless', 'phy80211')):
            continue
        def read(name):
            try:
                return (p / name).read_text().strip()
            except OSError:
                return '?'
        result.append({'name': p.name, 'mac': read('address'), 'carrier': read('carrier'),
                       'driver': (p / 'device/driver').resolve().name if (p / 'device/driver').exists() else '?'})
    return result


def summary(a):
    safe = copy.deepcopy(a)
    safe['accounts']['root_password_hash'] = '(set)'
    if safe['accounts'].get('user'):
        safe['accounts']['user']['password_hash'] = '(set)'
    if 'password' in safe['network']['wan']:
        safe['network']['wan']['password'] = '(set)'
    return json.dumps(safe, indent=2)


def display_summary(a, plan):
    """A readable confirmation, with the actual planned sizes and no secrets."""
    n = a['network']; lan = n['lan']; wan = n['wan']; fw = a['firewall']
    enabled = lambda value: 'yes' if value else 'no'
    lines = ['Erase entire disk: ' + a['disk'], 'Partitions:']
    for p in plan['partitions']:
        lines.append(f"  p{p['number']} {p['role']}: {p['size_mib']} MiB {p.get('fs', 'FAT32' if p['number'] == 1 else 'squashfs')}")
    lines += ['LAN ports: ' + ', '.join(n['lan_ports']),
              f"LAN: {lan['ipaddr']}  mask {lan['netmask']}",
              f"DHCP: {enabled(lan['dhcp'])}  start {lan['start']}  count {lan['limit']}",
              f"WAN: {wan['proto'].upper()}  port {n.get('wan_port') or 'none'}"]
    if wan['proto'] == 'static':
        lines += [f"  {wan['ipaddr']}  mask {wan['netmask']}  gateway {wan['gateway']}",
                  '  DNS: ' + ', '.join(wan['dns'])]
    if wan['proto'] == 'pppoe':
        lines.append('  Username: ' + wan['username'] + '  password: set')
    lines += ['IPv6: ' + enabled(n['ipv6']),
              f"NAT: {enabled(fw['masq'])}  full-cone: {enabled(fw['fullcone'] and fw['masq'])}  LAN to WAN: {enabled(fw['lan_to_wan'])}",
              'Root password: set']
    user = a['accounts'].get('user')
    lines.append(('User: ' + user['name'] + '  password: set  GNOME at boot: ' + enabled(user['gnome_autostart'])) if user else 'Regular user: none')
    return '\n'.join(lines) + '\n'
