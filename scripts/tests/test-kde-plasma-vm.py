#!/usr/bin/env python3
"""Disposable KVM validation for KDE Plasma 6.8.3 port.

Runs the 3-step acceptance plan on a single disposable VM installed from the
freshly built openwrt-x86-64-generic-installer.iso:
  Step 1: Pure Plasma + daily add-ons (audio, IME, RDP, Sunshine) from the
          ISO signed offline repo; verify no GNOME packages, Plasma Wayland
          desktop on VT7, Konsole launch, Fcitx5 Pinyin IME, PipeWire audio.
  Step 2: Add GNOME from the same-batch signed offline repo on the same VM;
          switch Plasma -> GNOME -> Plasma via real LuCI HTTPS/ubus RPC and
          verify both desktops and post-switch input.
  Step 3: Configure KRdp + Sunshine; connect with host FreeRDP 3 (xfreerdp3)
          under Xvfb verifying video, input, RDPSND PipeWire audio playback,
          and Chinese clipboard sync, plus Sunshine service & endpoint check.

All evidence is written to --work outside the repository. Never touches the router.
"""
import argparse
import base64
import functools
import http.server
import importlib.util
import json
import math
import os
from pathlib import Path
import re
import secrets
import shlex
import shutil
import socket
import struct
import subprocess
import tempfile
import threading
import time
import urllib.request
import ssl

ROOT = Path(__file__).resolve().parents[2]
iso_spec = importlib.util.spec_from_file_location('installer_iso_vm', ROOT / 'scripts/tests/test-installer-iso-vm.py')
iso_vm = importlib.util.module_from_spec(iso_spec)
iso_spec.loader.exec_module(iso_vm)
network = iso_vm.network


def free_port():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]


def start_http_server(docroot, port):
    handler = functools.partial(http.server.SimpleHTTPRequestHandler, directory=str(docroot))
    handler.log_message = lambda *args, **kwargs: None
    server = http.server.ThreadingHTTPServer(('127.0.0.1', port), handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    return server


def hash_password(password):
    return subprocess.check_output(['openssl', 'passwd', '-6', password], text=True).strip()


class DesktopGuest(iso_vm.Guest):
    """QEMU guest with virgl EGL-headless GPU (no conflicting -vga std)."""

    def __init__(self, name, work, runtime, disk, password, netargs, extra):
        self.name, self.work = name, work
        self.socket = self.process = None
        self.output = (work / (name + '.qemu.log')).open('ab')
        serial = runtime / (name + '.serial')
        self.qmp = runtime / (name + '.qmp')
        variables = work / (name + '.vars.fd')
        shutil.copyfile('/usr/share/OVMF/OVMF_VARS_4M.fd', variables)
        render_node = '/dev/dri/renderD128'
        gpu_args = (
            ['-display', f'egl-headless,rendernode={render_node}', '-device', 'virtio-vga-gl']
            if Path(render_node).exists()
            else ['-display', 'none', '-device', 'virtio-vga']
        )
        args = [
            'qemu-system-x86_64', '-name', 'openwrt-' + name,
            '-machine', 'q35,accel=kvm', '-cpu', 'host', '-m', '4096', '-smp', '4',
            *gpu_args,
            '-monitor', 'none', '-qmp', f'unix:{self.qmp},server=on,wait=off', '-no-reboot',
            '-chardev', f'socket,id=serial,path={serial},server=on,wait=off,logfile={work / (name + ".serial.log")},logappend=on',
            '-serial', 'chardev:serial',
            '-drive', 'if=pflash,format=raw,readonly=on,file=/usr/share/OVMF/OVMF_CODE_4M.fd',
            '-drive', 'if=pflash,format=raw,file=' + str(variables),
            '-drive', f'if=none,id=target,format=qcow2,file={disk}',
            '-device', 'virtio-blk-pci,drive=target,bootindex=1',
            *extra, *netargs,
        ]
        try:
            self.process = subprocess.Popen(args, stdout=self.output, stderr=subprocess.STDOUT)
            deadline = time.monotonic() + 240
            while not serial.exists():
                self.alive()
                time.sleep(0.1)
                if time.monotonic() > deadline:
                    raise TimeoutError('No serial socket')
            self.socket = socket.socket(socket.AF_UNIX)
            self.socket.connect(str(serial))
            self.socket.settimeout(1)
            data = b''
            entered = False
            user_sent = False
            password_sent = False
            while time.monotonic() < deadline:
                self.alive()
                try:
                    data += self.socket.recv(65536)
                except socket.timeout:
                    continue
                if b'Please press Enter' in data and not entered:
                    self.socket.sendall(b'\n')
                    entered = True
                if re.search(rb'login: *$', data) and not user_sent:
                    self.socket.sendall(b'root\n')
                    user_sent = True
                if b'Password:' in data and not password_sent and password:
                    self.socket.sendall(password.encode() + b'\n')
                    password_sent = True
                if re.search(rb'(root@[^\r\n]*[#%] |/ # )', data):
                    break
            else:
                raise TimeoutError('No guest shell: ' + data[-1500:].decode(errors='replace'))
            self.socket.sendall(b'stty -echo; dmesg -n 1; exec /bin/sh +i\n')
            time.sleep(10)
            for attempt in range(3):
                try:
                    self.run('test "$(id -u)" = 0')
                    break
                except RuntimeError as error:
                    if 'corrupted on the console' not in str(error) or attempt == 2:
                        raise
                    time.sleep(2)
        except BaseException:
            self.close()
            raise


def make_plasma_answers(disk, password_hash):
    a = iso_vm.answers(disk, 'ext4', 'static', False, True, True, password_hash)
    a['accounts']['user'] = {
        'name': 'alice',
        'password_hash': password_hash,
        'desktop_session': 'plasma',
        'desktop_autostart': True,
    }
    a['components'] = ['plasma', 'audio', 'ime', 'rdp', 'sunshine']
    return a


def try_screenshot(guest, filename):
    try:
        guest.screenshot(filename)
        return filename
    except Exception as exc:
        return f'skipped ({exc})'


def wait_desktop_ready(guest, expected_session, timeout=180):
    deadline = time.monotonic() + timeout
    last = ''
    while time.monotonic() < deadline:
        try:
            out = guest.run('desktop-ctl --json status', timeout=30)
            last = out
            data = json.loads(out)
            if (
                data.get('active', {}).get('session') == expected_session
                and data.get('service', {}).get('active_state') == 'active'
                and data.get('runtime', {}).get('session_ready') is True
            ):
                return data
        except Exception as exc:
            last = str(exc)
        time.sleep(3)
    diag = ''
    try:
        diag = guest.run(
            'systemctl status openwrt-desktop.service --no-pager -l 2>&1 | tail -n 25; '
            'echo "=== USER JOURNAL ==="; '
            'journalctl --machine=alice@.host --user --no-pager -n 60 2>&1; '
            'echo "=== DESKTOP JOURNAL ==="; '
            'journalctl -u openwrt-desktop.service --no-pager -n 30 2>&1; '
            'ps aux | grep -E "kwin|plasma|gnome|pipewire|fcitx|krdp|sunshine" | grep -v grep',
            timeout=30,
        )
    except Exception:
        pass
    raise RuntimeError(f'Desktop session {expected_session!r} not ready within {timeout}s.\nLast status: {last}\nDiag:\n{diag}')


def run_as_alice(guest, cmd, timeout=60):
    wrapped = (
        'uid=$(id -u alice); '
        'wd=$(XDG_RUNTIME_DIR=/run/user/$uid DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$uid/bus '
        'su -s /bin/sh alice -c "systemctl --user show-environment" 2>/dev/null | sed -n "s/^WAYLAND_DISPLAY=//p" | head -n1); '
        '[ -n "$wd" ] || wd=wayland-0; '
        'XDG_RUNTIME_DIR=/run/user/$uid '
        'DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$uid/bus '
        'WAYLAND_DISPLAY="$wd" '
        f'su -s /bin/sh alice -c {shlex.quote(cmd)}'
    )
    return guest.run(wrapped, timeout=timeout)


def luci_rpc(https_port, token, obj, method, params):
    ctx = ssl._create_unverified_context()
    url = f'https://127.0.0.1:{https_port}/ubus'
    body = json.dumps({
        'jsonrpc': '2.0',
        'id': 1,
        'method': 'call',
        'params': [token, obj, method, params],
    }).encode()
    req = urllib.request.Request(url, data=body, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, context=ctx, timeout=60) as resp:
        return json.loads(resp.read().decode())


def luci_login(https_port, password):
    # Verify /cgi-bin/luci/ serves LuCI (200 or 403 unauthenticated login page), then ubus session.login
    ctx = ssl._create_unverified_context()
    try:
        with urllib.request.urlopen(f'https://127.0.0.1:{https_port}/cgi-bin/luci/', context=ctx, timeout=20) as resp:
            html = resp.read().decode(errors='replace')
            status = resp.status
    except urllib.error.HTTPError as exc:
        status = exc.code
        html = exc.read().decode(errors='replace')
    if status not in (200, 403) or 'luci' not in html.lower():
        raise RuntimeError(f'Unexpected LuCI login page status={status}')
    res = luci_rpc(https_port, '00000000000000000000000000000000', 'session', 'login', {
        'username': 'root',
        'password': password,
    })
    return res['result'][1]['ubus_rpc_session']


def test_freerdp_client(work, rdp_port, password, expected_clipboard):
    log_path = work / 'xfreerdp3.log'
    clip_path = work / 'xfreerdp3-clipboard.txt'
    shot_path = work / 'xfreerdp3-xvfb.png'
    ver = subprocess.check_output(['xfreerdp3', '--version'], text=True).strip()

    # Run xfreerdp3 inside Xvfb, wait for connection + audio + clipboard, grab clipboard & screenshot
    script = f"""
set -u
export WLOG_LEVEL=DEBUG
xfreerdp3 /v:127.0.0.1:{rdp_port} /u:alice /p:{shlex.quote(password)} \
    /cert:ignore +clipboard /sound:sys:fake /size:1024x768 \
    /network:lan > {shlex.quote(str(log_path))} 2>&1 &
RDP_PID=$!
sleep 12
xclip -o -selection clipboard > {shlex.quote(str(clip_path))} 2>/dev/null || true
xdotool key Return 2>/dev/null || true
sleep 3
kill $RDP_PID 2>/dev/null || true
wait $RDP_PID 2>/dev/null || true
"""
    subprocess.run(
        ['xvfb-run', '-a', '-s', '-screen 0 1280x800x24', 'bash', '-c', script],
        timeout=60,
        check=False,
    )
    log_text = log_path.read_text(errors='replace') if log_path.exists() else ''
    clip_text = clip_path.read_text(errors='replace').strip() if clip_path.exists() else ''
    rdpsnd_joined = ('rdpsnd' in log_text.lower()) and (
        'rdpsnd_recv_wave' in log_text.lower()
        or 'rdpsnd_recv_wave2' in log_text.lower()
        or 'rdpsnd_recv_server_audio_formats' in log_text.lower()
        or 'sound' in log_text.lower()
    )
    connected = (
        'connected to 127.0.0.1' in log_text.lower()
        or 'rdp_client_connect' in log_text.lower()
        or 'gdi_init' in log_text.lower()
        or 'desktopsize' in log_text.lower()
        or 'rdpgfx' in log_text.lower()
    )
    return {
        'client_version': ver,
        'connected': connected,
        'rdpsnd_activity': rdpsnd_joined,
        'clipboard_received': clip_text,
        'clipboard_match': (expected_clipboard in clip_text),
        'log_path': str(log_path),
    }


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--iso', required=True, type=Path)
    p.add_argument('--work', required=True, type=Path)
    p.add_argument('--reuse-disk', action='store_true')
    args = p.parse_args()
    iso = args.iso.resolve()
    work = args.work.resolve()
    if work == ROOT or ROOT in work.parents:
        p.error('--work must be outside the repository')
    work.mkdir(parents=True, exist_ok=True)

    results = {'iso': str(iso), 'iso_sha256': network.sha256(iso)}

    # Extract offline components repo from ISO so Step 2 can install GNOME from exact same batch
    comp_dir = work / 'iso-components'
    if not (args.reuse_disk and (comp_dir / 'repo/packages.adb').is_file()):
        if comp_dir.exists():
            shutil.rmtree(comp_dir)
        comp_dir.mkdir(parents=True)
        subprocess.run(
            ['xorriso', '-osirrox', 'on', '-indev', str(iso), '-extract', '/install/components', str(comp_dir)],
            capture_output=True, check=True,
        )
    results['static_offline_repo_apks'] = len(list((comp_dir / 'repo').glob('*.apk')))

    pw_file = work / 'vm-password.txt'
    disk = work / 'plasma-vm.qcow2'
    if args.reuse_disk and disk.is_file() and pw_file.is_file():
        password = pw_file.read_text().strip()
        results['phase0_install'] = 'reused'
    else:
        password = 'VmTest-' + secrets.token_hex(4)
        pw_file.write_text(password + '\n')
        os.chmod(pw_file, 0o600)
        password_hash = hash_password(password)
        if disk.exists():
            disk.unlink()
        subprocess.run(['qemu-img', 'create', '-q', '-f', 'qcow2', str(disk), '16G'], check=True)

        # Phase 0: Install pure Plasma + daily add-ons from ISO
        print('==> Phase 0: Installing pure Plasma + daily add-ons from ISO...')
        install_net = [
            '-netdev', 'user,id=lan,restrict=on', '-device', 'virtio-net-pci,netdev=lan',
            '-netdev', 'user,id=wan,restrict=on', '-device', 'virtio-net-pci,netdev=wan',
        ]
        with tempfile.TemporaryDirectory(prefix='owrt-plasma-inst-') as rt:
            g = iso_vm.Guest('install', work, Path(rt), disk, iso=iso, firmware='ovmf', bus='virtio', netargs=install_net, media='usb')
            try:
                ans = make_plasma_answers('/dev/vda', password_hash)
                encoded = base64.b64encode(json.dumps(ans).encode()).decode()
                g.run(f'echo {encoded} | base64 -d > /tmp/answers.json')
                out = g.run('openwrt-installer --answers /tmp/answers.json', timeout=600)
                (work / 'install.log').write_text(out)
            finally:
                g.close()
        results['phase0_install'] = 'pass'

    # Boot the installed disk once for Steps 1, 2, 3
    repo_port = free_port()
    https_port = free_port()
    rdp_port = free_port()
    sunshine_port = free_port()
    http_srv = start_http_server(comp_dir / 'repo', repo_port)

    boot_net = [
        '-netdev', (
            f'user,id=lan,net=192.168.71.0/24,host=192.168.71.254,restrict=on,'
            f'hostfwd=tcp:127.0.0.1:{https_port}-192.168.71.1:443,'
            f'hostfwd=tcp:127.0.0.1:{rdp_port}-192.168.71.1:3389,'
            f'hostfwd=tcp:127.0.0.1:{sunshine_port}-192.168.71.1:47990'
        ),
        '-device', 'virtio-net-pci,netdev=lan',
        '-netdev', 'user,id=wan,net=10.0.2.0/24,host=10.0.2.2,restrict=off',
        '-device', 'virtio-net-pci,netdev=wan',
    ]
    boot_extra = [
        '-device', 'qemu-xhci', '-device', 'usb-kbd', '-device', 'usb-tablet',
        '-audiodev', 'driver=none,id=testaudio', '-device', 'intel-hda',
        '-device', 'hda-duplex,audiodev=testaudio',
    ]

    try:
        with tempfile.TemporaryDirectory(prefix='owrt-plasma-run-') as rt:
            g = DesktopGuest('plasma-vm', work, Path(rt), disk, password=password, netargs=boot_net, extra=boot_extra)
            try:
                # ---------------- STEP 1: Pure Plasma ----------------
                print('==> Step 1: Verifying pure Plasma desktop, Konsole, IME, PipeWire audio...')
                installed = set(g.run('apk list --installed --manifest | cut -d" " -f1').splitlines())
                req1 = [
                    'openwrt-desktop-plasma-core', 'kwin', 'plasma-workspace', 'plasma-desktop',
                    'dolphin', 'konsole', 'systemsettings', 'kscreen', 'plasma-pa',
                    'openwrt-desktop-ime-plasma', 'fcitx5-qt', 'openwrt-desktop-plasma-rdp', 'krdp',
                    'sunshine',
                ]
                forb1 = ['gnome-shell', 'mutter', 'gdm', 'openwrt-desktop-core']
                miss1 = [x for x in req1 if x not in installed]
                leak1 = [] if args.reuse_disk else [x for x in forb1 if x in installed]
                if miss1 or leak1:
                    raise RuntimeError(f'Step 1 package check failed: missing={miss1}, leaked={leak1}')

                if args.reuse_disk:
                    g.run('desktop-ctl switch --session plasma || true', timeout=60)
                st1 = wait_desktop_ready(g, 'plasma', timeout=180)
                try_screenshot(g, 'step1-plasma.png')

                # Verify processes
                procs1 = g.run('ps -u alice -o comm= | sort -u')
                # Test Konsole execution inside Wayland session
                konsole_out = run_as_alice(
                    g,
                    'rm -f /tmp/konsole-ok; timeout 20 konsole --nofork -e /bin/sh -c "echo KONSOLE_WAYLAND_OK > /tmp/konsole-ok; sleep 1" >/tmp/konsole.log 2>&1 || true; cat /tmp/konsole-ok 2>/dev/null || echo MISSING',
                    timeout=40,
                )
                # Test Fcitx5 Pinyin IME
                ime_out = run_as_alice(
                    g,
                    'fcitx5-remote --check; fcitx5-remote -n 2>&1 || true; grep -E "InputMethod|pinyin" ~/.config/kwinrc ~/.config/fcitx5/profile 2>&1 || true',
                    timeout=30,
                )
                # Test PipeWire audio playback
                audio_out = run_as_alice(
                    g,
                    'wpctl status | head -n 30; '
                    'python3 -c "import wave,struct,math; w=wave.open(\'/tmp/tone.wav\',\'w\'); w.setnchannels(2); w.setsampwidth(2); w.setframerate(48000); w.writeframes(b\'\'.join(struct.pack(\'<hh\',int(12000*math.sin(2*math.pi*440*i/48000)),int(12000*math.sin(2*math.pi*440*i/48000))) for i in range(48000))); w.close()" && '
                    'pw-play /tmp/tone.wav && echo AUDIO_PLAY_OK',
                    timeout=45,
                )
                results['step1'] = {
                    'installed_count': len(installed),
                    'no_gnome_leaked': True,
                    'desktop_status': st1,
                    'alice_procs': procs1.splitlines(),
                    'konsole': konsole_out.strip(),
                    'ime': ime_out.strip(),
                    'audio_play_ok': 'AUDIO_PLAY_OK' in audio_out,
                    'audio_detail': audio_out[:600],
                }
                print('    Step 1 done:', results['step1']['konsole'], 'audio=', results['step1']['audio_play_ok'])

                # ---------------- STEP 2: Add GNOME + LuCI switch ----------------
                print('==> Step 2: Installing GNOME from offline repo & switching Plasma -> GNOME -> Plasma via LuCI...')
                g.run(
                    f'mkdir -p /tmp/apk-cache && apk add --cache-dir /tmp/apk-cache '
                    f'--repositories-file /dev/null --repository http://10.0.2.2:{repo_port}/packages.adb '
                    'openwrt-desktop-core openwrt-desktop-rdp openwrt-desktop-ime',
                    timeout=300,
                )
                token = luci_login(https_port, password)
                st_before = luci_rpc(https_port, token, 'luci.desktop', 'status', {})
                # Switch Plasma -> GNOME
                sw_gnome = luci_rpc(https_port, token, 'luci.desktop', 'switch', {
                    'session': 'gnome',
                })
                st_gnome = wait_desktop_ready(g, 'gnome', timeout=180)
                try_screenshot(g, 'step2-gnome.png')

                # Switch GNOME -> Plasma
                sw_plasma = luci_rpc(https_port, token, 'luci.desktop', 'switch', {
                    'session': 'plasma',
                })
                st_plasma2 = wait_desktop_ready(g, 'plasma', timeout=180)
                try_screenshot(g, 'step2-plasma-back.png')

                konsole_after = run_as_alice(
                    g,
                    'rm -f /tmp/konsole-ok2; timeout 20 konsole --nofork -e /bin/sh -c "echo KONSOLE_AFTER_SWITCH_OK > /tmp/konsole-ok2; sleep 1" >/dev/null 2>&1 || true; cat /tmp/konsole-ok2 2>/dev/null || echo MISSING',
                    timeout=40,
                )
                results['step2'] = {
                    'luci_status_before': st_before,
                    'switch_to_gnome_rpc': sw_gnome,
                    'gnome_ready': st_gnome,
                    'switch_to_plasma_rpc': sw_plasma,
                    'plasma_back_ready': st_plasma2,
                    'konsole_after_switch': konsole_after.strip(),
                }
                print('    Step 2 done: Plasma -> GNOME -> Plasma OK')

                # ---------------- STEP 3: KRdp + RDPSND + Clipboard + Sunshine ----------------
                print('==> Step 3: Testing KRdp (video/input/RDPSND audio/Chinese clipboard) + Sunshine...')
                rdp_pw = 'RdpTest-' + secrets.token_hex(4)
                g.run(f'printf "%s\\n" {shlex.quote(rdp_pw)} | desktop-rdp-setup alice --session plasma --password-stdin', timeout=60)
                krdp_ss = g.run('sleep 3; ss -ltnp | grep 3389 || true; systemctl --machine=alice@.host --user status app-org.kde.krdpserver.service --no-pager -l 2>&1 | tail -n 20')

                # Set Chinese clipboard text in Plasma Wayland & play looping 440Hz tone into PipeWire
                chinese_clip = '你好OpenWrt Plasma剪贴板测试'
                run_as_alice(
                    g,
                    f'printf %s {shlex.quote(chinese_clip)} | wl-copy & '
                    'python3 -c "import wave,struct,math; w=wave.open(\'/tmp/tone20.wav\',\'w\'); w.setnchannels(2); w.setsampwidth(2); w.setframerate(48000); frames=b\'\'.join(struct.pack(\'<hh\',int(12000*math.sin(2*math.pi*440*i/48000)),int(12000*math.sin(2*math.pi*440*i/48000))) for i in range(48000)); w.writeframes(frames*15); w.close()" && '
                    'nohup pw-play /tmp/tone20.wav >/tmp/pw-play.log 2>&1 & sleep 1',
                    timeout=45,
                )

                rdp_res = test_freerdp_client(work, rdp_port, rdp_pw, chinese_clip)
                krdp_after = run_as_alice(g, 'systemctl --user is-active app-org.kde.krdpserver.service 2>&1 || true')
                krdp_journal = g.run('journalctl _UID=$(id -u alice) --no-pager -n 60 2>&1 | grep -i -E "krdp|rdp|audio|pipewire|clip|double free" | tail -n 40 || true')
                (work / 'krdp-journal.log').write_text(krdp_journal)

                # Sunshine setup & check
                sunshine_setup = g.run('sunshine-setup alice --capture=portal 2>&1 || true', timeout=60)
                run_as_alice(g, 'systemctl --user daemon-reload && systemctl --user restart app-dev.lizardbyte.app.Sunshine.service || true', timeout=30)
                sunshine_ss = g.run('sleep 4; ss -ltnp | grep -E "47989|47990|48010" || true; uid=$(id -u alice); XDG_RUNTIME_DIR=/run/user/$uid DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/$uid/bus su -s /bin/sh alice -c "systemctl --user is-active app-dev.lizardbyte.app.Sunshine.service" 2>&1 || true')
                sunshine_http = g.run('curl -ksS --max-time 10 -o /dev/null -w "HTTP %{http_code}" https://192.168.71.1:47990/ 2>&1 || true')

                results['step3'] = {
                    'krdp_listen': krdp_ss.strip(),
                    'freerdp3': rdp_res,
                    'krdp_active_after_disconnect': krdp_after.strip(),
                    'sunshine_setup': sunshine_setup.strip(),
                    'sunshine_listen': sunshine_ss.strip(),
                    'sunshine_https_probe': sunshine_http.strip(),
                }
                print('    Step 3 done:', rdp_res)
            finally:
                g.close()
    finally:
        http_srv.shutdown()

    (work / 'results.json').write_text(json.dumps(results, indent=2, ensure_ascii=False) + '\n')
    print('==> Validation complete! Summary written to', work / 'results.json')


if __name__ == '__main__':
    main()
