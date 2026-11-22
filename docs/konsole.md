# Konsole (KDE terminal emulator)

Konsole is shipped as an **optional** package on top of the native GNOME
desktop. It is not part of `openwrt-desktop-core` and not enabled in
`configs/x86-64-systemd-desktop.config`; selecting `configs/konsole.config` is
what pulls in Qt 6 and the KDE Frameworks 6 stack.

## What is built

| Component | Version | Notes |
| --- | --- | --- |
| Konsole | 26.08.3 | KDE Gear, built with `-DWITH_LIBSSH=OFF` |
| KDE Frameworks 6 | 6.20.0 | Frameworks and QML modules under `package/custom/` |
| Qt 6 | 6.9.3 | `feeds/video` qt6base with xcb, Wayland, DBus and PrintSupport |
| Qt Quick | 6.9.3 | Required by KNewStuff and KF6 I18n QML |
| Qt Multimedia | 6.9.3 | FFmpeg backend, PulseAudio output |
| Qt TextToSpeech | 6.9.3 | Flite backend |
| Qt Wayland | 6.9.3 | Client platform plugins for the GNOME session |
| Platform | xcb + wayland | Native Wayland with XWayland fallback |

The framework set is the transitive closure of Konsole's link line plus the
frameworks needed by its optional features: KArchive, KAttica, KBookmarks,
KCodecs, KColorScheme, KCompletion, KConfig, KConfigWidgets, KCoreAddons,
KCrash, KDBusAddons, KGlobalAccel, KGuiAddons, KI18n, KIconThemes, KIO,
KItemViews, KJobWidgets, KNewStuff, KNotifications, KNotifyConfig, KPackage,
KParts, KPty, KService, KSolid, KSonnet, KTextWidgets, KWidgetsAddons,
KWindowSystem and KXmlGui. The download dialog uses the QML modules from
Kirigami, KCMUtils, KCoreAddons and Qt Quick. The Breeze icon theme supplies
the native icon set for KDE applications.

The full desktop feature set is enabled:

- **KNewStuff** downloads colour schemes with the profile dialog's
  "Get New…" button.
- **Qt Multimedia** plays iTerm2 inline-audio escape sequences through
  FFmpeg and the PulseAudio API (PipeWire's Pulse server).
- **Sonnet** uses the Hunspell backend with an English (US) dictionary.
- **KTextWidgets** speaks selected text through Qt TextToSpeech and Flite.
- **KPty** records terminal sessions through `libutempter`.

## Build-time code generation

Konsole turns `settings/KonsoleSettings.kcfgc` into C++ at build time through
`kconfig_add_kcfg_files()`. That helper normally runs `KF6::kconfig_compiler`
inside the cross build, where the compiler executable cannot run on the
host. `kf6-kconfig` therefore also builds a host copy of
`kconfig_compiler_kf6` (`kf6-kconfig/host`, installed under
`staging_dir/hostpkg`), and the Konsole recipe passes
`-DKF6_HOST_TOOLING=$(STAGING_DIR_HOSTPKG)/lib/cmake`. A local KConfig patch
(`package/custom/kf6-kconfig/patches/0001-use-host-tooling-when-requested.patch`)
uses that tooling whenever the variable is set. OpenWrt sets
`CMAKE_SYSTEM_NAME=Linux` for both host and target, so CMake's own
`CMAKE_CROSSCOMPILING` flag is not a reliable switch for this tree.

Qt Wayland also needs `qtwaylandscanner` at build time.
`package/custom/qt6wayland` builds it as a host tool; a package patch lets
that host build succeed without Wayland libraries, which the scanner does not
use.

## Enabling the optional stack

The fragment is merged by hand (there is no automatic fragment tool):

```sh
./scripts/kconfig.pl + .config configs/konsole.config > .config.new
mv .config.new .config
make defconfig
```

Build order is resolved by the package dependencies. For an incremental
build:

```sh
make package/konsole/compile V=s
```

The complete image can then be built with the usual
`build-and-publish.py build-only` or `build-and-publish.sh` workflow. Because
this is an optional package, plain `make` and the publication wrappers only
include it when the fragment is present in `.config`.

On a running system the package and its dependency closure install with:

```sh
apk add konsole
```

## Running

Start `Konsole` from the GNOME application grid or from a terminal. The
launcher inherits the desktop session's D-Bus address and display. The
Konsole package pulls in both QPA plugins. Qt uses the session type and
display environment to prefer native Wayland and fall back to xcb (XWayland).
The session exports `QT_IM_MODULE=fcitx` and
`XMODIFIERS=@im=fcitx`; `fcitx5-qt` provides the Qt platform input context
module, so CJK input works in Konsole and other Qt applications.

Configuration is the normal KDE one: `~/.config/konsolerc`, profiles under
`~/.local/share/konsole/`, colour schemes and keyboard layouts from
`/usr/share/konsole/`.

## Framework build choices

The recipes enable the full feature set where the dependencies are packaged,
and only avoid features that would need another framework not present:

| Recipe | Option | Reason |
| --- | --- | --- |
| `kf6-ki18n` | `-DBUILD_WITH_QML=ON` | KNewStuff links `KF6::I18nQml` |
| `kf6-kconfig` | `-DKCONFIG_USE_QML=OFF` | KConfig's QML bindings are not needed |
| `kf6-kcoreaddons` | `-DKCOREADDONS_USE_QML=ON` | The KNewStuff page imports `org.kde.coreaddons` |
| `kf6-kwindowsystem` | `-DKWINDOWSYSTEM_WAYLAND=ON`, `-DKWINDOWSYSTEM_X11=ON` | Native Wayland and XWayland |
| `kf6-sonnet` | `-DSONNET_USE_QML=OFF`, Hunspell backend | Spell checking through Hunspell |
| `kf6-ktextwidgets` | `-DWITH_TEXT_TO_SPEECH=ON` | Qt TextToSpeech with Flite |
| `kf6-kpty` | `-DUTEMPTER_EXECUTABLE=/usr/lib/utempter/utempter` | utmp/wtmp accounting |

`kf6-kservice` additionally sets `CMAKE_BINARY_SUBDIR:=build` because its
`CMakeLists.txt` refuses an in-source build.

## Desktop integration and current limits

- **Icons and style:** the Breeze icon theme is packaged as
  `kf6-breeze-icons`; KIconThemes selects it by default. Individual icons
  that Breeze does not provide fall back to the desktop icon theme. The
  Breeze widget style is not packaged, so Qt uses the Fusion style.
- **Input methods:** `fcitx5-qt` is built for Qt 6 with both the xcb and
  Wayland paths. Latin and CJK input work through Fcitx5; the session sets
  `QT_IM_MODULE=fcitx`.
- **Spell checking:** Sonnet's Hunspell backend is enabled with an English
  (US) dictionary. Additional languages need another dictionary package.
- **Text-to-speech:** the Flite backend synthesises English speech. The
  speech-dispatcher backend is not packaged.
- **Login accounting:** KPty uses `libutempter`; its install script ensures
  the `utmp` group exists and assigns it to the setgid helper. Systemd
  tmpfiles manages the accounting files.
- **Single instance:** KDBusAddons registers Konsole on the session bus, so
  opening a second instance reuses the running one when the session bus is
  available.
- **KIO:** Local file and bookmark operations work through KIO workers. KAuth,
  KWallet and KDED are not packaged; features that need them are absent.

## Dependencies added outside `package/custom`

The `feeds/video` Qt6 packages gained the pieces the desktop needs. These
changes are mirrored in `patches/feeds/0050-video-qt6-desktop.patch`:

- `qt6base`: new `qt6base-dbus`, `qt6base-printsupport`,
  `qt6base-plugin-platforms-xcb` and `qt6base-plugin-inputcontexts-ibus`
  subpackages; xcb/DBus/PrintSupport/Wayland/fontconfig/harfbuzz configure
  switches; host Qt now builds Widgets and DBus tools (`uic`,
  `qdbuscpp2xml`, `qdbusxml2cpp`) needed by KF6. The xcb build also enables
  `FEATURE_xlib` and `FEATURE_xcb_xlib`: KF6WindowSystem's X11 backend asks Qt
  for a `Display*`, and without Xlib support that pointer is NULL and Konsole
  crashes while creating its main window.
- `libxkbcommon`: builds the X11 support library and splits
  `libxkbcommon-x11` out of the base package.
- `wayland`: stages `wayland.xml`, which Qt Wayland and KWindowSystem need
  when generating protocol code.

New `package/custom` recipes provide Qt Quick, Qt Multimedia, Qt TextToSpeech,
Qt Wayland, Plasma Wayland protocols, Flite, Hunspell with an English
dictionary, libutempter and `fcitx5-qt`.

The build-only `qt6tools` package (Qt Linguist host tools plus the target
`Qt6LinguistTools` CMake package) is a build dependency of the KF6 recipes:
`ecm_install_po_files_as_qm()` needs `lrelease` for the framework message
catalogs. It is not installed at runtime.

Five small X.Org libraries that Qt's xcb plugin links are new custom
packages: `libxcb-image`, `libxcb-keysyms`, `libxcb-render-util`, `libxcb-wm`
(icccm/ewmh) and `libxcb-cursor`.

All new recipes are registered in `configs/custom-package-updates.json`.

## Troubleshooting

- `qt.qpa.plugin: could not load the Qt platform plugin "xcb"` — install
  `qt6base-plugin-platforms-xcb` and the five `libxcb-*` packages; the plugin
  must be in `/usr/lib/qt6/plugins/platforms/libqxcb.so`.
- `Failed to load platform plugin "wayland"` — install
  `qt6waylandclient`; the session falls back to XWayland through xcb.
- Konsole segfaults in `XQueryExtension` while creating its window — the
  installed Qt was built without `FEATURE_xlib`/`FEATURE_xcb_xlib`, so
  `QX11Application::display()` is NULL. Rebuild `qt6base` from this tree
  (the recipe enables both when the xcb plugin is selected).
- No CJK input in Qt applications — check that `fcitx5-qt` is installed,
  that `QT_IM_MODULE=fcitx` is set in the session, and that Fcitx5 is
  running. `fcitx5-diagnose` reports the Qt input context state.
- No audio output — `qt6multimedia` needs a running PulseAudio-compatible
  server; the GNOME profile provides one through PipeWire.
- Missing fonts or empty glyph boxes — install `fontconfig`, the DejaVu fonts
  and `noto-sans-symbols2` (the desktop image already has them).
- KService warnings about a missing `ksycoca6` database are transient; the
  database is rebuilt by `kbuildsycoca6` on demand.

See [konsole-validation.md](konsole-validation.md) for the build and runtime
checks.
