# Desktop Package Decoupling Validation

## Scope

This record covers **host-side source checks, unit tests, LuCI JS/ucode tests,
Kconfig normalization, signed APK package compilation, clean-root signed APK
dependency closure checks, host APK 3.0.5 rolling-upgrade handoff checks, and
disposable KVM validation (new same-batch ISO matrix + live VM rolling upgrade
from pre-decoupling ISO)** on 2026-11-23 (baseline commit `1a6def2a22`).

- **Disposable VM validation**: Run in KVM (`qemu-system-x86_64`, OVMF + BIOS,
  `swtpm` TPM2 emulator, local signed HTTP feed). Evidence saved under
  `/srv/openwrt-validation/desktop-decoupling-validation-20261123/` (`vm-receipt.json`,
  serial logs, and local display screenshots `gnome-core-notpm.png`, `full-gnome.png`).
- **RDP client validation**: Verified `xfreerdp3 +auth-only` TLS/NLA authentication,
  reconnection, post-LAN-IP-recovery reconnection, and post-rolling-upgrade-reboot
  reconnection (`rc=0`). Interactive RDP display/input/audio/clipboard streaming
  remains to be exercised with a graphical client.
- **Moonlight client validation**: Not run (`moonlight` / `moonlight-qt` is not
  installed on this host); Sunshine user service activation (`sunshine_active: true`,
  both fresh and post-upgrade via legacy `gnome-session.target.wants` link) was
  verified inside the VMs.
- **Physical router installation & feed publication**: Not run (requires separate
  explicit user authorization).

## Built Package & ISO Artifacts

- **New same-batch installer ISO**: `bin/systemd/targets/x86/64-glibc/openwrt-x86-64-generic-installer.iso`
  (`7b5bbd2fcf52484099586d133111ea5949b81fc6744508b4f9a6614acb3a62e4`)
- **Pre-decoupling baseline ISO (for live VM rolling upgrade)**: `/srv/openwrt-validation/desktop-decoupling-validation-20261123/old-installer.iso`
  (`c269beb07ddfd6e9e3d90f8874ad6461ca70db741ef4ba0815683111d9c7b887`, shipping `openwrt-desktop-core` 38, `openwrt-desktop` 38, `sunshine` r15)
- **Signed base index**: `bin/systemd/packages/x86_64/base/packages.adb`
  (`8194f853a7c008506cf0e67a676e03fcefcdc9fad63a6a3a99e4371b24d0b3b8`)
- **Host rolling-upgrade baseline feed**: `/srv/openwrt-feeds/public/current` (`snapshots/20261123T065704.485364Z`) + `/srv/openwrt-feeds/public/kernel-upgrades`

| Package | Path | SHA-256 |
| --- | --- | --- |
| `openwrt-desktop-base` | `bin/systemd/packages/x86_64/base/openwrt-desktop-base-41.apk` | `4e0d57beb008219e0ee21d385e5d0fe77090a378691608ccdeee04cad8b1f39a` |
| `openwrt-desktop-core` | `bin/systemd/packages/x86_64/base/openwrt-desktop-core-41.apk` | `54071173cee7afbf4a3f85a78b0c09e4b13a73fbc441b0d39c85ca153f8bd126` |
| `openwrt-desktop-rdp` | `bin/systemd/packages/x86_64/base/openwrt-desktop-rdp-41.apk` | `b2a6fe21cf2cd86482fbd2cf36b00c091fa7ff3070dd40e7f2f1a4c3b951d3c6` |
| `openwrt-desktop` | `bin/systemd/packages/x86_64/base/openwrt-desktop-41.apk` | `7e6fbc27089e6223723a9c729f044c357b5c16d0990d0a2a617916363b1bda85` |
| `luci-app-desktop` | `bin/systemd/packages/x86_64/base/luci-app-desktop-1.0.0-r2.apk` | `81a9e0630033a797d67f58725a1f8ff2ee29fd5ed69c09137d666823ce25d13f` |
| `luci-i18n-desktop-zh-cn` | `bin/systemd/packages/x86_64/base/luci-i18n-desktop-zh-cn-26.327.28028~1a6def2.apk` | `50ab363a35ba84bcdd748cb3eacadd83d1fbf587280c10cd3755add72e137d86` |
| `openwrt-desktop-audio` | `bin/systemd/packages/x86_64/base/openwrt-desktop-audio-1-r7.apk` | `2dbbd0181d4c65cfda0652d89afe56ff20bc9c7c094e2a054c8be84c36272e4f` |
| `openwrt-desktop-ime-base` | `bin/systemd/packages/x86_64/base/openwrt-desktop-ime-base-1-r7.apk` | `1308329c67b7dae4126b9e543f7c212980bd95e81a4bd5545cf3a4417e222c57` |
| `openwrt-desktop-ime` | `bin/systemd/packages/x86_64/base/openwrt-desktop-ime-1-r7.apk` | `2d9e19a7c245f77fb7d358b47daacfd02209a9ab562ec951781a0d4fba768bf6` |
| `openwrt-flatpak-base` | `bin/systemd/packages/x86_64/base/openwrt-flatpak-base-1-r14.apk` | `29d54c246ac5fe1963ec99118fd2a49877b4e4a8949d17fdb4e026a1431ddaa9` |
| `openwrt-flatpak` | `bin/systemd/packages/x86_64/base/openwrt-flatpak-1-r14.apk` | `c0ed88539578cbee2a34b502c517120fa405551b02c488789e371bc072a0a8f0` |
| `openwrt-appimage` | `bin/systemd/packages/x86_64/base/openwrt-appimage-1-r7.apk` | `51f214a20d6d0c44c4354f9c4e4fa05cf1a8fa1b1895ffbb09f314c8132a49a0` |
| `sunshine` | `bin/systemd/packages/x86_64/base/sunshine-2026.914.233613-r16.apk` | `490f4b43449259037e2a3ada6c4d8c4840b0be72e045eee96bcdec499cafe6ca` |

## Host & Package Checks

| Check | Result |
| --- | --- |
| `./scripts/feeds update -i -a && ./scripts/feeds install -a && make defconfig` | PASS (`openwrt-desktop-base`, `openwrt-desktop-ime-base`, `openwrt-flatpak-base` selected cleanly) |
| `make package/custom/{openwrt-desktop,luci-app-desktop,openwrt-desktop-audio,openwrt-desktop-ime,openwrt-flatpak,openwrt-appimage,sunshine}/compile -j12 V=s` + `make package/index V=s` + `make package/install target/install -j12 V=s` | PASS (13 signed APKs, `packages.adb`, and same-batch installer ISO built cleanly) |
| `scripts/tests/test-installer-components-vm.py --static-only` on new ISO | PASS (base squashfs excludes `openwrt-desktop-base`, `openwrt-desktop-ime-base`, `openwrt-flatpak-base`, and all desktop/GNOME packages) |
| `python3 scripts/tests/test-desktop-sessions.py` | PASS (5/5 tests) |
| `python3 scripts/tests/test-luci-desktop.py` + `node scripts/tests/test-luci-desktop-view.js` | PASS (4/4 ucode tests + Node.js view assertions incl. `not_applicable` and `selection_error`) |
| `python3 scripts/tests/test-rtkit-desktop.py`, `test-sunshine-gnome.py`, `desktop-rdp-config.py`, `test-gnome-keyring.py`, `test-desktop-audio.py`, `test-desktop-ime.py`, `test-installer-components.py`, `test-custom-package-updates.py` | PASS (87/87 tests) |
| Clean-root signed APK closure (`openwrt-desktop-base` + `luci-app-desktop` + `openwrt-desktop-audio` + `openwrt-desktop-ime-base` + `openwrt-flatpak-base` + `openwrt-appimage` + `sunshine`) | PASS (367 packages installed; 0 forbidden GNOME packages in closure) |
| Clean-root signed APK closure (`openwrt-desktop-core`, full GNOME, no-desktop router) | PASS (341 / 487 / 157 packages respectively; exact boundaries verified) |
| Host APK 3.0.5 rolling upgrade without `--force-overwrite` (old full GNOME, old GNOME core, add-on-only world pinning `openwrt-desktop-core`) | PASS (zero conflicts, conffile preservation, ownership handoff to `-base` subpackages) |
| `git diff --check` | PASS |

## Disposable KVM & Client Checks

| Check | Result |
| --- | --- |
| **Scenario 1 (`new_base_and_dummy`, new ISO OVMF/ext4)**: Router-only install (`1037` pkgs, 0 desktop pkgs) -> install common + all generic add-ons (`1229` pkgs, 0 GNOME pkgs) -> 0-session LuCI RPC (`selection_error`, `keyring_credential: not_applicable`, `rdp_available: false`) -> `dummy` Wayland test session `desktop-setup alice` (no `/etc/desktop/gnome`), `openwrt-desktop-services.service` + `openwrt-audio-session.target` + `openwrt-flatpak-session.target` start/stop with `graphical-session.target` via LuCI `stop` (with `desktop.main.enabled=1`, verified `/run/openwrt-desktop/manual-stop` prevents DRM VT-release hotplug auto-restart) and `start` (clears `manual-stop`) | PASS |
| **Scenario 2 (`new_gnome_core`, new ISO BIOS/CD-ROM/SATA/btrfs, `gnome` only)**: `1228` pkgs (no RDP/audio/IME/Sunshine/Flatpak/AppImage); cold boot without TPM2 -> plaintext fallback (`keyring: plaintext`, `unlocked: true`, `rdp_available: false`, `Virtual-1`, `xdg-desktop-portal-gnome`, `pipewire.socket`, `gnome-core-notpm.png`); reboot with `swtpm` TPM2 -> `desktop-setup alice` auto-seals to TPM2 SRK (`keyring: tpm2`, `unlocked: true`) | PASS |
| **Scenario 3 (`new_full_gnome`, new ISO OVMF/xfs + `swtpm` TPM2)**: `1404` pkgs; TPM2 keyring unlocked, `Virtual-1` (`full-gnome.png`), Fcitx5/Pinyin profile + Kimpanel enabled, PipeWire/WirePlumber + Flatpak portal + `openwrt-desktop-services.service` + `openwrt-gnome-remotes.service` + `sunshine.service` (`sunshine_active: true`) + `gnome-remote-desktop.service` active; LAN IP change (`192.168.71.1 -> 192.168.71.2 -> 192.168.71.1`) resync; `xfreerdp3 +auth-only` initial connect, reconnect, and post-IP-recovery reconnect (`rc=0`) | PASS |
| **Scenario 4a (`rolling_upgrade` old full GNOME, old ISO -> new signed HTTP feed, scripts enabled, NO `--force-overwrite`)**: `openwrt-desktop-core-38` -> `openwrt-desktop-base-41` + `openwrt-desktop-core-41` + `-base` splits; `/etc/config/desktop` & `/etc/pam.d/openwrt-desktop` local edits preserved and owned by `openwrt-desktop-base-41` (`.apk-new`: `/etc/config/desktop.apk-new`, `/etc/pam.d/openwrt-desktop.apk-new`, `/etc/config/ttyd.apk-new`); `desktop-ctl --json action restart` PASS; full VM reboot with persisted `swtpm` TPM2 -> TPM2 keyring unlocked, `openwrt-fcitx5.service`, `wireplumber.service`, `gnome-remote-desktop.service`, and `sunshine.service` (via legacy `gnome-session.target.wants` link, `old_full_reboot_sunshine_active: true`) all active; `xfreerdp3 +auth-only` reconnect PASS (`rc=0`) | PASS |
| **Scenario 4b (`rolling_upgrade` old GNOME core, old ISO -> new signed HTTP feed, scripts enabled, NO `--force-overwrite`)**: `/etc/config/desktop` local edit preserved and owned by `openwrt-desktop-base-41`; RDP not pulled in (`rdp_available: false`); full VM reboot -> GNOME active and keyring unlocked | PASS |

## Remaining Checks

1. **Interactive graphical RDP client**: verify rendered frames, keyboard/mouse input, RDP audio, and bidirectional clipboard (host `xfreerdp3 +auth-only` covered TLS/NLA auth and reconnect only).
2. **Real Moonlight client**: not installed on this host (`moonlight` / `moonlight-qt` missing); verify video/input/audio/reconnect from a Moonlight client.
3. **Feed publication & physical router deployment**: requires separate explicit user authorization and live-router preflight.
