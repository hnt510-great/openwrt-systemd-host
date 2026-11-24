# KDE Plasma 6.8.3 Validation Record

- **Date**: 2026-11-24
- **Installer ISO**: `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-installer.iso`
- **ISO SHA-256**: `03bdb6efe163f860e9a68c9ab22fc1e1ce5213010abf63a823428849c76af257`
- **Kernel release**: `7.3.5-86-openwrt`
- **Evidence directory**: `/srv/openwrt-validation/kde-plasma-validation-20261124/`

## Validation Scope

- **Source & host tests**: Executed in full on the build host (Python `unittest`, Node.js LuCI view assertions, APK offline component dependency closure & forbidden-package sanity checks, `git diff --check`).
- **Disposable KVM VM validation**: Executed end-to-end from scratch in a single disposable OVMF KVM VM (`scripts/tests/test-kde-plasma-vm.py`) with `virtio-vga-gl` (`egl-headless` on `/dev/dri/renderD128`), `intel-hda` + `hda-duplex`, and real host FreeRDP 3.33.1 (`xfreerdp3`) under `xvfb-run`.
- **Physical router hardware**: **Not tested** (per project guardrails; no deployment to the physical router or LAN feed publication was performed).
- **Moonlight client**: Not installed on this headless build host; Sunshine enrollment and `app-dev.lizardbyte.app.Sunshine.service` activation were verified in-guest, while end-to-end Moonlight client streaming was not run.

## Results Summary

| Check | Scope | Result |
| --- | --- | --- |
| `python3 scripts/tests/test-desktop-sessions.py` | Host unit test | PASS (6/6) |
| `python3 scripts/tests/test-luci-desktop.py` | Host unit test | PASS (4/4) |
| `node scripts/tests/test-luci-desktop-view.js` | Host LuCI view test | PASS |
| `python3 scripts/tests/test-installer-components.py` | Host unit test | PASS (12/12) |
| `python3 scripts/tests/test-openwrt-installer.py` | Host unit test | PASS (11 passed, 1 skipped) |
| `python3 scripts/tests/test-custom-package-updates.py` | Host unit test | PASS (51/51) |
| `build-installer-components.py` offline repo & forbidden-package checks | Build host | PASS (525 signed offline APKs; zero GNOME/Flatpak/IME leaks in pure `plasma`) |
| Step 0: Offline ISO install (`components: ["plasma","audio","ime","rdp","sunshine"]`) | Disposable KVM VM | PASS |
| Step 1: Pure Plasma isolation (no `gnome-shell`/`mutter`/`gdm`/`openwrt-desktop-core`) | Disposable KVM VM | PASS (1397 packages, 0 GNOME leaks) |
| Step 1: Plasma 6.8.3 Wayland session ready (`kwin_wayland`, `plasmashell`, `kactivitymanagerd`, `xdg-desktop-portal-kde`, `gnome-keyring-daemon`) | Disposable KVM VM | PASS (`session_ready: true`, `keyring_unlocked: true`) |
| Step 1: Konsole launch inside Plasma Wayland | Disposable KVM VM | PASS (`KONSOLE_WAYLAND_OK`) |
| Step 1: Fcitx5 Chinese Pinyin (`openwrt-fcitx5-plasma.service`) | Disposable KVM VM | PASS (`fcitx5-remote --check` = 1, `DefaultIM=pinyin`, `pinyin` addon loaded) |
| Step 1: PipeWire 1.6.11 audio playback (`pw-play`) | Disposable KVM VM | PASS (`AUDIO_PLAY_OK`) |
| Step 2: Same-VM signed offline GNOME install (`openwrt-desktop-core`, `openwrt-desktop-rdp`, `openwrt-desktop-ime`) | Disposable KVM VM | PASS (verified against ISO public key) |
| Step 2: LuCI HTTPS + `/ubus` `luci.desktop.switch` (`Plasma → GNOME → Plasma`) | Disposable KVM VM | PASS (both sessions reached `session_ready: true`; `KONSOLE_AFTER_SWITCH_OK`) |
| Step 3: KRdp LAN-only bind (`desktop-rdp-setup alice --session plasma`) | Disposable KVM VM | PASS (`192.168.71.1:3389` only) |
| Step 3: FreeRDP 3.33.1 (`xfreerdp3`) connection, RDPSND audio, Chinese clipboard | Host client -> KVM VM | PASS (`connected: True`, 115+ 48kHz stereo S16 PCM RDPSND Wave2 packets, clipboard `你好OpenWrt Plasma剪贴板测试` matched) |
| Step 3: KRdp stability after client disconnect | Disposable KVM VM | PASS (`app-org.kde.krdpserver.service` remained `active`) |
| Step 3: Sunshine setup (`sunshine-setup alice --capture=portal`) | Disposable KVM VM | PASS (`app-dev.lizardbyte.app.Sunshine.service` `active`; Moonlight client not installed on host) |
| Physical router deployment / LAN feed publication | Physical device | NOT RUN (out of scope without explicit authorization) |

## Issues Found & Resolved During VM Validation

1. **`kwin` XWayland flag**: `-DKWIN_BUILD_X11=OFF` disabled XWayland in KWin 6.8, causing `kwin_wayland_wrapper --xwayland` to fail with `Unknown option 'xwayland'`. Switched to `-DKWIN_BUILD_X11=ON`.
2. **Qt SQLite driver & GLib event loop**: `kactivitymanagerd` aborted without `qt6base-plugin-sqldrivers-sqlite` (blocking `plasmashell`), and `plasma-pa` required Qt's GLib event loop (`-DFEATURE_glib=ON` + `+glib2` in `qt6base-core`). Both added and verified.
3. **Plasma systemd boot**: `startplasma-wayland` fell back to classic `plasma_session` because OpenWrt omits `xdg-desktop-autostart.target`. Added `startkderc` `General/systemdBoot=force` in `desktop-plasma-settings`.
4. **KRdp config filename & disconnect cleanup**: `krdpserver` reads `krdpserverrc` (not `krdprc`), and `rdpsnd_server_context_free()` freed non-heap `server_formats`/`src_format` pointers on client disconnect. Fixed both and verified `krdpserver` stays `active` after disconnect.
5. **Fcitx5 & hot-switch cleanup**: Added `openwrt-fcitx5-plasma.service` (bound to `plasma-workspace.target`) in `openwrt-desktop-ime-plasma`, moved `desktop-ime-session` to `openwrt-desktop-ime-base`, added `systemctl --user daemon-reload` in `desktop-session`, and stopped `graphical-session.target` + `openwrt-fcitx5-plasma.service` in `sessions.d/plasma`'s `desktop_session_stop`.
