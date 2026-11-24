# Chinese Pinyin (Fcitx5) on the GNOME and KDE Plasma Desktops

Fcitx5 Chinese Pinyin support is split into three packages in
`package/custom/openwrt-desktop-ime` (`1-r9`):

- `openwrt-desktop-ime-base`: DE-agnostic Fcitx5 base (`openwrt-desktop-base`,
  `fcitx5-chinese-addons`, `fcitx5-gtk`, `noto-sans-cjk-sc`), default config
  templates under `/usr/share/openwrt-desktop-ime/`, and session init helpers
  (`/usr/libexec/desktop-ime-init`, `/usr/libexec/desktop-ime-session`).
- `openwrt-desktop-ime`: GNOME integration (`openwrt-desktop-ime-base`,
  `openwrt-desktop-core`, `gnome-shell-extension-kimpanel`, and user unit
  `openwrt-fcitx5.service` with `--enable=ibusfrontend` for GNOME/GTK/Xwayland).
- `openwrt-desktop-ime-plasma`: KDE Plasma integration
  (`openwrt-desktop-ime-base`, `fcitx5-qt`), paired with `fcitx5`'s
  `/usr/share/applications/org.fcitx.Fcitx5.desktop` so KWin launches Fcitx5
  directly over the Wayland input-method protocol (`WAYLAND_SOCKET`).

No cloud Pinyin service is enabled. The desktop runs the same input method
locally, over LAN RDP (`gnome-remote-desktop` or `krdp`), and over
Sunshine/Moonlight.

## Configuration and build

Select `CONFIG_PACKAGE_openwrt-desktop-ime=y` (for GNOME, included in
`configs/x86-64-systemd-desktop.config`) and/or
`CONFIG_PACKAGE_openwrt-desktop-ime-plasma=y` (for KDE Plasma, included in
`configs/plasma.config` and `configs/plasma-packages.config`), or merge
`configs/desktop-ime.config`. The offline installer ISO also provides the
optional `ime` component (`depends_any: ["gnome", "plasma"]`), which selects
the matching desktop integration package automatically.

To compile the package on x86_64/glibc:

```sh
make defconfig
make -j3 package/custom/openwrt-desktop-ime/compile V=s
```

`libime` compiles its dictionary generators for the target and runs them with
the matching toolchain loader and explicit library search path. Bundled,
hash-pinned upstream data archives avoid downloads from the CMake build.
The default PNG candidate theme works without librsvg; custom SVG themes are
not supported by this build.

## Session integration and shortcuts

- **GNOME 51**: `sessions.d/gnome` exports `QT_IM_MODULE=fcitx` and
  `openwrt-fcitx5.service` runs Fcitx5 with Kimpanel providing the GNOME Shell
  indicator and candidate popup.
- **KDE Plasma 6.8.3**: `desktop-plasma-settings` configures KWin's
  `[Wayland] InputMethod=/usr/share/applications/org.fcitx.Fcitx5.desktop` and
  `VirtualKeyboardEnabled=true`, and `sessions.d/plasma` exports
  `XMODIFIERS=@im=fcitx` for XWayland apps. KWin spawns Fcitx5 directly with
  `WAYLAND_SOCKET` attached so Wayland apps (including RDP keystrokes via
  `krdpserver`) use KWin's native input-method protocol.

Do not start a duplicate Fcitx5 daemon manually or via a second autostart entry.
For a fresh profile, the session starts in English. Focus a text field, press
**Control+Space** (or **Control+Shift+Return**), type `nihao`, and press
**Space** to commit `你好`. Press the trigger again to return to English. Number
keys select candidates; Escape cancels composition.

## User settings

On first use, `/usr/libexec/desktop-ime-init` copies defaults to
`${XDG_CONFIG_HOME:-$HOME/.config}/fcitx5/`: `config`, `profile`, and
`conf/classicui.conf`. Existing files and symlinks are preserved, and package
upgrades never overwrite personal dictionaries or learning history. Default
triggers in `/usr/share/openwrt-desktop-ime/config` are:

```ini
[Hotkey/TriggerKeys]
0=Control+space
1=Control+Shift+Return
```

Run `fcitx5-remote -r` in the desktop session after editing settings.

## macOS RDP clients

In macOS Microsoft Remote Desktop / Windows App, switch to **Connections >
Keyboard Mode > Scancode** (`Control+Command+K`). Unicode mode translates local
input into characters for the local macOS IME and may not forward remote IME
shortcuts.

Because macOS commonly intercepts `Control+Space` for local input-source
switching, **Control+Shift+Return (Enter)** is configured as a second trigger
out of the box. Keep the Mac input source on ABC/English when composing with
remote Pinyin.

Reference: https://learn.microsoft.com/en-us/windows-app/input-keyboard-mouse-touch-pen?tabs=macos

## Firefox profile focus troubleshooting

If Firefox accepts English keystrokes but never forwards the IME shortcut,
inspect `focusmanager.testmode` in `about:config`. This automation preference
must be `false` for normal desktop use (automated Marionette profiles can leave
it `true`, causing `mLastFocusedWindow=0x0` rejections). Set
`user_pref("focusmanager.testmode", false);` in `user.js` and restart Firefox.

For automated IME tests in a disposable profile, disable the recommended
automation override (`remote.prefs.recommended=false`) and explicitly set
`focusmanager.testmode=false`, asserting native window focus before injecting
keys.

## Validation

Host source tests:

```sh
python3 scripts/tests/test-desktop-ime.py
python3 scripts/tests/test-custom-package-updates.py
```

Desktop session and decoupling validation results are recorded in
[gnome-desktop-validation.md](gnome-desktop-validation.md),
[desktop-package-decoupling-validation.md](desktop-package-decoupling-validation.md),
and [kde-plasma-validation.md](kde-plasma-validation.md).
