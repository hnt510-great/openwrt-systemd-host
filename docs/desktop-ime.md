# Chinese Pinyin on the Weston/RDP desktop

Select `CONFIG_PACKAGE_openwrt-desktop-ime=y` (also included in the saved
x86_64/systemd desktop configuration). This installs Fcitx5, the libime offline
Chinese dictionaries, Chinese addons, the GTK3 module, and Noto Sans CJK SC.
The desktop runs the same input method locally and over its existing RDP mirror.
No cloud Pinyin service is enabled.

Build on Linux x86_64 using the glibc target:

```sh
make defconfig
make -j3 package/custom/openwrt-desktop-ime/compile V=s
```

`libime` compiles its dictionary generators for the target and runs them with
the matching toolchain loader and explicit library search path. Bundled,
hash-pinned upstream data archives avoid downloads from the CMake build.
The default PNG candidate theme works without librsvg; custom SVG themes are
not supported by this build. GTK3 applications work on Wayland and Xwayland
through their input module. Xlib/XIM-only and Qt applications are outside this
package's scope; there is no Qt input module or XIM frontend in this build.

After installing the packages, the next desktop session starts Fcitx through
Weston's `[input-method]` entry. This follows the upstream [Weston integration](https://fcitx-im.org/wiki/Using_Fcitx_5_on_Wayland#Weston).
Weston supplies its privileged Wayland socket;
Fcitx must stay in the foreground. Do not start a duplicate daemon through
systemd, D-Bus activation, or a second desktop autostart entry.
A desktop restart closes the current desktop applications, so schedule it when
ready. Reconnecting RDP alone does not replace an already-running session.

For a fresh profile, the session starts in English. Focus a text field, press
**Ctrl+Shift+Space**, type `nihao`, and press **Space** to commit `你好`.
Press Ctrl+Shift+Space again to return to English. Number keys select candidates;
Escape cancels composition. The candidate popup uses a Chinese-capable font.
Firefox uses the GTK3 Fcitx module; the session also supplies an explicit module
cache because the base GTK package does not generate one.

## macOS RDP clients

Use **Control+Shift+Enter (Return)** in macOS Microsoft Remote Desktop.
**Control+Shift+Space** remains available for Windows RDP and Moonlight.
These shortcuts do not use Command or
Option and avoids the default Control+Space and Control+Option+Space shortcuts
for switching macOS input sources ([Apple shortcut reference](https://support.apple.com/en-us/102650)). Keep the Mac input source on ABC/English
when composing with remote Pinyin, and use the RDP client's physical/scancode
keyboard mode if it offers one. A client that sends only already-composed
Unicode text cannot forward the remote IME's raw keyboard shortcut. Custom
macOS shortcuts can still intercept any chosen combination.

## User settings

On first use, the session copies defaults to
`${XDG_CONFIG_HOME:-$HOME/.config}/fcitx5/`: `config`, `profile`, and
`conf/classicui.conf`. Existing files and symlinks are preserved. Updates never
replace a personal dictionary or learning history. An existing Fcitx profile
keeps its current methods and shortcuts; add Pinyin and edit its trigger list
if needed:

```ini
[Hotkey/TriggerKeys]
0=Control+Shift+space
1=Control+Shift+Return
```

Run `fcitx5-remote -r` in the desktop session after editing settings. The
packaged defaults remain in `/usr/share/openwrt-desktop-ime/` for reference.

## Validation

Source tests:

```sh
python3 scripts/tests/test-desktop-ime.py
python3 scripts/tests/desktop-rdp-config.py
python3 scripts/tests/test-custom-package-updates.py
```

The IME tests exercise first-use setup, custom XDG paths, private file modes,
existing settings and symlink preservation, inherited Wayland file descriptors,
and Weston configuration with and without the integration package.

For guest acceptance, install the signed matching userspace packages into a
disposable guest; verify offline dependency simulation first. In Firefox over
RDP, toggle Pinyin with scan-code events, type `nihao`, commit with Space, and
read the field back as `你好`. Toggle back and check literal English input.
Also check the candidate popup, reconnect, and restart persistence. Repeat
with the actual macOS client to confirm its local shortcut forwarding.
Build and source tests alone do not establish guest, physical-router, or macOS
client acceptance. Feed publication and physical deployment are separate steps.

## Results on 2026-10-26

The integration package and its dependencies built successfully. Signature and
integrity verification passed for the Fcitx5, libime, Chinese addon, GTK module,
and desktop integration APKs. The existing desktop package was rebuilt as release 15 for initial validation.
Deployment uses release 16 to preserve an already-published release 15.
All 48 focused IME/session, RDP configuration, updater, and package-metadata
unit checks passed, along with shell syntax and whitespace checks.

The staged target binaries passed an NLA-authenticated RDP test inside a
bubblewrap namespace with its own network, user bus, runtime directory, home,
and temporary account. Actual scan-code events activated Pinyin with
Ctrl+Shift+Space (Fcitx state 2), composed `nihao`, committed `你好`, then returned
to English (state 1) and produced exactly `你好abc` in a native GTK3 entry.
A compositor screenshot of the RDP output showed the candidate popup with
`你好` first. This also exercises the GTK3 module and its explicit module cache.
The smoke test caught and fixed a missing mandatory Chaizi dictionary.

To reproduce after building, with bubblewrap and the matching host FreeRDP 3
client libraries installed:

```sh
python3 scripts/tests/desktop-ime-smoke.py
```

Results, logs, and the candidate screenshot are written under
`bin/validation/desktop-ime/`. The test removes its temporary keys and SAM file.
Its debug capture protocol is enabled only in the isolated test compositor.
These initial checks validate target userspace on the host kernel; no VM was
used. The subsequent physical deployment is recorded below. Firefox itself and
the actual macOS RDP client remain outside the completed acceptance checks.

## Signed publication and physical deployment

Published and deployed on 2026-10-26 after an exact nine-APK offline simulation.
The userspace snapshot is `20261026T063221.121689Z`, served under
`http://apk.example.invalid:8088/abi/7.3~5001c59b1072ebdf1a2ed551a854f37a-r1/`.
The `base`, `packages`, and custom projection indexes include the new packages.
Publication used the staged router upgrade/ELF audit with the existing kernel
snapshot held unchanged. Router index refresh and HTTP SHA256 checks of all
nine published payloads passed.

The exact transaction on `192.0.2.1` added Fcitx5 `5.1.23-r1`, Chinese addons
`5.1.15-r1`, GTK integration `5.1.7-r1`, libime `1.1.17-r1`, iso-codes `4.18.0-r1`,
Boost iostreams/random `1.92.0-r2`, and openwrt-desktop-ime `1-r1`; it upgraded
openwrt-desktop from release 15 to 16. No base library or kernel was upgraded.
The world file retains its previous entries plus `openwrt-desktop-ime`.

The desktop was restarted to activate the packaged input-method entry and GTK
module cache. Weston and Fcitx5 run as the configured ordinary desktop user;
RDP again listens on `192.0.2.1:3389`. The generated profile contains US English,
Pinyin, and the Control+Shift+Space trigger. A test input context on the physical
user bus processed that shortcut, committed exactly `你好` from `nihao`, and
returned to English passthrough. This physical engine check is distinct from
the earlier isolated end-to-end RDP test; actual macOS client forwarding still
needs a reconnect and client-side test.

Boot ID, running kernel generation g30, installed kernel packages, kernel health,
network/firewall/DHCP/desktop configuration, and RDP SAM/TLS hashes were preserved.
The kernel publication snapshot remained unchanged. The two existing failed
hostname-sync units were present before and after this deployment.
No machine reboot, firmware flash, or unrelated service restart was performed.

A timed rollback protected installation and activation; it was cancelled after
successful runtime and preservation checks. The signed fallback desktop package,
original runtime/configuration archive, world/database snapshots, and audit are
retained on the router in `/root/desktop-ime-backup-20261026T063434Z`.
The runtime archive preserves the installed release-15 file contents separately
from the published release-15 fallback APK. Local publication receipts,
transaction logs, the physical engine probe, and preservation audit are under
`bin/validation/desktop-ime-deploy-20261026/`.

## Firefox profile focus troubleshooting

If Firefox accepts English keystrokes but never forwards the IME shortcut,
inspect `focusmanager.testmode` in `about:config`. This automation preference
must be `false` for normal desktop use. A physical user profile was found with
`user_pref("focusmanager.testmode", true)` on 2026-10-26. Its IME/GTK module and
Fcitx input context were present; native-focus testing was therefore required
in addition to module and daemon checks.

The affected user's `prefs.js` and existing `user.js` were backed up under
`~/.local/state/desktop-ime-focus-backup-20261026T121748Z/`. A single override,
`user_pref("focusmanager.testmode", false);`, was appended to `user.js` for the
next startup. After restart approval, Firefox's preferences and session recovery
were also backed up under
`~/.local/state/desktop-ime-session-20261026T122231Z/`. Firefox was stopped
normally and reopened with its original profile and restored session. Verification
confirmed the same original window and tab, without exposing their URLs.

A normal Firefox tab (without Marionette) then passed the physical machine's
native input path: it had native focus, Control+Shift+Space selected Pinyin,
`nihao` plus Space committed `你好`, and switching back allowed `abc`.
The textarea's actual value was `你好abc`. The temporary tab was closed afterward.
This test used a temporary server-side input device; the Windows client's
shortcut forwarding still needs user confirmation. Its existing RDP connection
from `192.0.2.118` remained established and Fcitx stayed running.

For automated IME tests, disable the recommended automation preference override
(`remote.prefs.recommended=false`) and explicitly set
`focusmanager.testmode=false` in a disposable profile. Assert that the test
window has native focus before injecting keys. Marionette's usual automation
focus mode can otherwise produce `mLastFocusedWindow=0x0` rejections and a false
IME failure; an unfocused test window must fail the harness before any typing.
Diagnostic attempts and the profile repair record are retained under
`bin/validation/desktop-ime-windows-rdp/`. No browser backend, RDP credential,
remote-client configuration, or global shortcut was changed for this repair.

## macOS Microsoft Remote Desktop / Windows App

For the remote Fcitx5 Pinyin engine, use the client's **Connections > Keyboard
Mode > Scancode** setting. Microsoft documents **Control+Command+K** as the
shortcut for this mode. Then focus a text field in the remote Firefox window
and use **Control+Shift+Space** (the physical Control key).

Unicode mode translates local input into characters and is intended for uses
including the local macOS IME; it may not preserve the remote IME's shortcut
path. A macOS-specific failure with working Windows-client switching does not
by itself prove which mode or local shortcut interception caused it. Confirm
client mode and retest before changing the server's working trigger.

Reference: https://learn.microsoft.com/en-us/windows-app/input-keyboard-mouse-touch-pen?tabs=macos

### Confirmed macOS RDP shortcut repair (2026-10-26)

The Mac was already in Scancode mode. A passive Fcitx D-Bus monitor received
Control and Shift press/release events for repeated Control+Shift+Space attempts,
but no Space events within those chords. Standalone Space arrived normally.
This locates the loss before the Fcitx input context; it does not distinguish
macOS interception, client handling, and compositor processing. Moonlight
switching only changed the shared IME state and did not prove RDP switching.

Added Control+Shift+Return as a second trigger in the package defaults and the
physical user's existing configuration. Reloaded Fcitx configuration through
its controller without restarting Firefox or the desktop. The original user
configuration is backed up under
`~/.local/state/desktop-ime-macos-20261026T142328Z/`. The user confirmed the new
shortcut works in macOS RDP. Default package release 2 contains the additional
trigger; existing user settings remain preserved by the first-use installer.
