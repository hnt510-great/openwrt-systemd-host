# Desktop Session Switcher & LuCI Control Validation

## Scope

This record covers **host-side source checks, unit tests, ucode/Node.js tests,
APK package compilation, and physical router live validation** for
`openwrt-desktop` (`PKG_RELEASE=40`) and `luci-app-desktop` (`1.0.0-r1`) on
2026-11-23.

- **Disposable VM validation**: Not run (installed and verified directly on
  physical router `192.0.2.1` per user authorization).
- **Physical router validation**: Installed signed APKs on `192.0.2.1`
  (`Linux OpenWrt 7.3.5-84-openwrt`) on 2026-11-23, caught and fixed a
  transient-unit reload bug when `/etc/systemd/system/openwrt-desktop.service.d/`
  drop-ins are present (released as `PKG_RELEASE=40`), and verified full
  end-to-end `ubus call luci.desktop action '{"verb":"restart"}'` on the live
  host.

## Built Package Artifacts

| Package | Path | SHA-256 |
| --- | --- | --- |
| `openwrt-desktop-core` | `bin/systemd/packages/x86_64/base/openwrt-desktop-core-40.apk` | `5f0bc94e0634438915190b2af054fb45a58cf0d27800eb37ac51d99db8f8fcd6` |
| `openwrt-desktop` | `bin/systemd/packages/x86_64/base/openwrt-desktop-40.apk` | `09f21d576e0d540c0432c47ba2f76f2bf294da09a442372aac5ede63af3985bb` |
| `openwrt-desktop-rdp` | `bin/systemd/packages/x86_64/base/openwrt-desktop-rdp-40.apk` | `48638b85b48fac38da7dafa1ab33f40d0e09dfd376abe0a97c9caffd7611f854` |
| `luci-app-desktop` | `bin/systemd/packages/x86_64/base/luci-app-desktop-1.0.0-r1.apk` | `ada8e6b92a2b8cccd5d6cd161948ca8c463dad9f14f51f65908bffc35270998d` |
| `luci-i18n-desktop-zh-cn` | `bin/systemd/packages/x86_64/base/luci-i18n-desktop-zh-cn-0.apk` | `fc431f01eac4e781e134acba56d881b145df40392dbd270f3b62b6ff8683785f` |

## Checks

| Check | Result |
| --- | --- |
| `./scripts/feeds update -i -a && ./scripts/feeds install -a` | PASS (indexed and linked `luci-app-desktop` and `openwrt-desktop`) |
| `make defconfig` with `CONFIG_PACKAGE_luci-app-desktop=y` | PASS |
| `make package/custom/openwrt-desktop/compile V=s` | PASS (`openwrt-desktop-core-39.apk` installs `sessions.d/gnome` and `/usr/sbin/desktop-ctl`) |
| `make package/custom/luci-app-desktop/compile V=s` | PASS (`luci-app-desktop-1.0.0-r1.apk` + `luci-i18n-desktop-zh-cn-0.apk`) |
| `python3 scripts/tests/test-custom-package-updates.py` | PASS (51/51 tests) |
| `python3 scripts/tests/test-desktop-sessions.py` | PASS (3/3 tests: `gnome` ↔ `dummy` switch, `active.env` old-session stop, cross-DE env cleanup, symlink/ID rejection, `desktop-ctl` drift & preflight) |
| `python3 scripts/tests/test-luci-desktop.py` | PASS (4/4 tests with `staging_dir/hostpkg/bin/ucode`: allowlisted argv, injection rejection, output cap, ACL read/write separation) |
| `node scripts/tests/test-luci-desktop-view.js` | PASS (status, dynamic sessions, drift banner, Save & Apply isolation, confirmation modal, read-only ACL, XSS safety) |
| `python3 scripts/tests/test-rtkit-desktop.py` | PASS (13/13 tests) |
| `python3 scripts/tests/test-sunshine-gnome.py` | PASS (2/2 tests) |
| `python3 scripts/tests/desktop-rdp-config.py` | PASS (4/4 tests) |
| `python3 scripts/tests/test-gnome-keyring.py` | PASS (1/1 isolated real `gnome-keyring-daemon` test) |
| `git diff --check` | PASS (no whitespace errors) |
| Physical router (`192.0.2.1`) `apk add` (`openwrt-desktop*` 40 + `luci-app-desktop` 1.0.0-r1 + `luci-i18n-desktop-zh-cn` 0) | PASS (`uci-history` revision 92) |
| Physical router live `ubus call luci.desktop action '{"verb":"restart"}'` + `status` | PASS (`active_state=active`, `main_pid=29764`, `n_restarts=0`, `active={session=gnome,user=desktop-user,kms_scheduling=high-priority,output=auto,mode=1920x1080}`, `keyring_credential=tpm2`, `keyring_unlocked=true`, `rdp_active=true`, `sunshine_active=true`, `audio_active=true`, `sessions=[gnome]`, `outputs=[HDMI-A-2]`, `systemctl --failed` empty) |

## Remaining Checks

- Open `Services -> Desktop` in the browser to visually inspect the LuCI page.
