# Konsole validation record

Date: 2026-11-22

## Scope

Optional, full-featured Konsole package on the x86/64 glibc systemd desktop
stack. The package is not part of the default desktop image and is not in
`configs/x86-64-systemd-desktop.config`. No router or VM image was built,
published or flashed, so there is no image path or SHA256; this record covers
source builds, package-level checks and host smoke tests of the cross-built
binaries. It does not cover the GNOME session on the physical router, and the
Wayland path was exercised only up to platform-plugin loading because no
Wayland compositor is available in the workspace.

## Build inputs

| Item | Value |
| --- | --- |
| Workspace | `/srv/openwrt` |
| Konsole | 26.08.3 |
| KDE Frameworks | 6.20.0 (32 packages, including Breeze Icons) |
| Qt base | 6.9.3 (`feeds/video`, `PKG_RELEASE:=4`) |
| Qt Quick / Multimedia / TextToSpeech / Wayland | 6.9.3 |
| Flite | 2.2 |
| Hunspell | 1.7.2, English (US) dictionary 4.0.0 |
| libutempter | 1.2.3 (pinned commit) |
| fcitx5-qt | 5.1.16 |
| Fragment | `configs/konsole.config` |
| Work config backup | `/srv/openwrt-validation/konsole-port/config.before` |
| Build logs | `/srv/openwrt-validation/konsole-port/` |

The optional fragment was merged into the working `.config`, `make defconfig`
was run, and the packages were built with direct package targets. The
working `.config` is restored from the backup after validation; the fragment
stays the opt-in mechanism.

## Checks

| Check | Result |
| --- | --- |
| Target Qt6 configures with `FEATURE_xcb=ON`, `FEATURE_dbus=ON`, `FEATURE_printsupport=ON`, `FEATURE_wayland=ON`, system fontconfig/harfbuzz | passed |
| Target Qt6 enables `FEATURE_xlib` and `FEATURE_xcb_xlib`; `libqxcb.so` links `libX11`/`libX11-xcb` | passed |
| `QX11Application::display()` returns a non-NULL `Display*` under the xcb platform plugin | passed |
| `qt6base-plugin-inputcontexts-ibus` is packaged | passed |
| `libxcb-image`, `libxcb-keysyms`, `libxcb-render-util`, `libxcb-wm`, `libxcb-cursor` build and pass ELF metadata | passed (all five) |
| `libxkbcommon` builds with X11 support and splits `libxkbcommon-x11` | passed |
| Target Qt Quick builds with QuickWidgets | passed |
| Target Qt Multimedia builds with FFmpeg and PulseAudio; plugin loads and enumerates two audio outputs | passed |
| Target Qt TextToSpeech builds with Flite; engine `flite`, locale `en_US`, five voices | passed |
| Target Qt Wayland builds; `libqwayland-generic.so` and shell-integration plugins load | passed (no compositor to connect to) |
| Hunspell library and English dictionary build; `hunspell -d en_US -l` flags misspellings | passed |
| libutempter builds; helper installed mode 2711; post-install creates the `utmp` group | passed |
| `fcitx5-qt` builds; platform input context plugin loads and advertises `fcitx`/`fcitx5` | passed |
| All 32 KF6 framework recipes build, including Breeze Icons | passed |
| Breeze icons install `breeze` and `breeze-dark` themes plus `/etc/xdg/kdeglobals` selecting `breeze`; Konsole declares the dependency | passed |
| Breeze icons package builds: 10 MB APK, no 24x24 PNG generation (host lacks Python lxml), scalable SVGs present | passed |
| Host `kconfig_compiler_kf6` is available through `KF6_HOST_TOOLING` | passed |
| Host `qtwaylandscanner` is built and used by the cross Qt Wayland build | passed |
| KNewStuff libraries, QML pieces and `knewstuff-dialog6` build and run | passed |
| Konsole builds and links KF6NewStuff, Qt6Multimedia, KPty and KWindowSystem | passed |
| Konsole package depends on `kf6-breeze-icons` | passed (APK metadata) |
| ELF ABI metadata generation for every package | passed (packages contain `elf.depends`/`elf.provides`) |
| Konsole package output | `bin/systemd/packages/x86_64/base/konsole-26.08.3-r1.apk` plus the framework/Qt dependency packages |
| `konsole --version` with target libraries | passed, prints `konsole 26.08.3` |
| `konsole --help` with target libraries | passed |
| GUI startup under Xvfb and a private D-Bus session | passed: main window `"openwrt : zsh — Konsole"` with `WM_CLASS ("konsole" "konsole")`, 793x423, shell process running |
| Session exits cleanly when its child command ends | passed (exit status 0) |
| `QT_IM_MODULE=fcitx` loads the fcitx5 Qt platform input context plugin | passed |
| `QT_QPA_PLATFORM=wayland` loads the Qt Wayland platform plugin and shell integration | passed (connection fails without a compositor, as expected) |

The host smoke tests run the target binaries directly because both the host
and the target are x86_64 glibc. They use the staged target root, the target
Qt plugins and, for the GUI tests, a host Xvfb display. Host programs (Xvfb,
`dbus-run-session`, `xdotool`) run without the target library path so they use
the host libraries. `/usr/lib/pulseaudio` is added to the target library path
for `libpulsecommon`.

## Issues found during validation

- OpenWrt configures CMake in the source directory; KService rejects that.
  `kf6-kservice` now sets `CMAKE_BINARY_SUBDIR:=build`.
- KF6 CMake packages must stage headers, linker names and `lib/cmake/KF6*`
  files. `include/kf6-package.mk` sets `CMAKE_INSTALL:=1`.
- Sonnet needs a spelling backend; the Hunspell plugin and dictionary are
  now packaged. QML bindings stay disabled because Konsole does not use them.
- KTextWidgets needs Qt TextToSpeech, which in turn needs Qt Multimedia for
  its Flite backend; both modules are now built.
- KPty needs utempter; `libutempter` is packaged and the helper path is
  passed at configure time.
- Host `extra-cmake-modules`, `kf6-kconfig` and `qt6wayland` must include
  `host-build.mk` before `cmake.mk`; otherwise the Autotools
  `Host/Configure/Default` overrides the CMake one.
- Qt Wayland's host build requires Wayland libraries it does not use; a
  package patch keeps that host build limited to the scanner.
- KWindowSystem's Wayland backend needs `wayland.xml`, which the `wayland`
  package now stages.
- With `FEATURE_xcb_xlib=OFF`, Qt's xcb plugin has no Xlib display and
  KF6WindowSystem's X11 backend dereferences a NULL `Display*` during startup.
  Enabling `FEATURE_xlib`/`FEATURE_xcb_xlib` while the xcb plugin is selected
  fixes the crash; the plugin then links `libX11`/`libX11-xcb`.
- CMake 4.4 no longer ships `FindPulseAudio`; Qt Multimedia gets a local
  pkg-config based module.
- Executable links through Qt Multimedia need
  `-Wl,-rpath-link,$(STAGING_DIR)/usr/lib/pulseaudio` because
  `libpulsecommon-17.0.so` lives outside `lib/`.
- `fcitx5-qt` installs its plugin into Qt's host plugin path unless
  `CMAKE_INSTALL_QT6PLUGINDIR` is set to `/usr/lib/qt6/plugins`.
- Breeze Icons wants Python lxml to generate 24x24 PNGs; it is built with
  `WITH_ICON_GENERATION=OFF` and ships the scalable/symbolic SVGs.

## Evidence

- Build logs: `/srv/openwrt-validation/konsole-port/`
  (`qt6-wayland-build.log`, `build-qt6multimedia.log`,
  `build-qt6speech.log`, `build-qt6wayland*.log`, `build-kf6-*.log`,
  `build-konsole-full2.log`)
- Host smoke logs: `/srv/openwrt-validation/konsole-port/smoke-konsole.log`,
  `konsole-window-test*.log`
- Probe logs: `/tmp/mediaprobe.log`, `/tmp/ttsprobe.log`,
  `/tmp/konsole-fcitx.log`, `/tmp/konsole-wayland.log`,
  `/tmp/knewstuff-help.log`
- Package output: `bin/systemd/packages/x86_64/base/` and
  `bin/systemd/packages/x86_64/video/`
- Original working configuration: `/srv/openwrt-validation/konsole-port/config.before`

## Integration fixes

The default, xcb-only, Wayland-only and Konsole configurations pass strict
Kconfig validation. The checks used temporary configuration files. The
Wayland-only configure options enable `xkbcommon` and leave xcb and
`xkbcommon-x11` disabled.

QtBase builds as `6.9.3-r5`; the rebuilt `libxkbcommon` and its X11 split
build as `1.13.2-r5`. The desktop and `libutempter` packages also build.
A temporary root with its own `utmp` group verified that the packaged
tmpfiles rule sets the helper to mode 2711 and uses the target group's GID.

Qt Quick, Kirigami, KCMUtils, KCoreAddons with its QML plugin, KNewStuff
and Konsole built successfully. An offline APK transaction installed
`konsole=26.08.3-r2` into a temporary root with the desktop profile's
`ca-bundle` provider. The transaction used the existing local feed
snapshots, the kernel feed and a temporary index of the new packages.
It pulled in both display backends, Fcitx5 Qt and the complete QML dependency
set.

Using the APK payloads from that root, an isolated headless GNOME Shell
session acknowledged the native Wayland surface and Konsole ran its child
shell. A separate Xvfb test verified automatic xcb fallback when the
Wayland compositor was unavailable and confirmed loading the Fcitx5 Qt
input context. A KNewStuff widget probe reached `QQuickWidget::Ready`
using a local catalog fixture. The probe logged a Kirigami
`OverlayDrawer.qml` width warning during initialization and loaded the page.
The host checks leave native keyboard input, Fcitx5 composition and a
download from the live catalog for target-session validation.

## Rolling publication

On 2026-11-22 the full fragment was merged into the working `.config` and
published with:

```sh
./scripts/build-and-publish.sh --rolling --allocate-rebuilds -j16
```

| Item | Value |
| --- | --- |
| Userspace snapshot | `/srv/openwrt-feeds/public/snapshots/20261122T002354.718935Z` |
| Kernel generation | 82 |
| Kernel snapshot | `/srv/openwrt-feeds/public/kernel-snapshots/1795307078803783891` |
| Published packages | 1407 |
| ELF files with metadata | 2465 |
| Router upgrade preflight | passed (receipt `1795307088202288076.json`) |

Generation 81 was already published and its kernel package bytes were
immutable, so the publisher reserved generation 82. New releases were
allocated for `libpcre2` (10.49-r6, configuration now builds the 16-bit
variant required by Qt6Core), `squashfs-tools-unsquashfs` (4.7.5-r5) and
`gnome-tweaks` (49.0-r3). The publication installed nothing on the router.

## Router installation

On 2026-11-22 the published rolling update was installed on the router over
SSH without rebooting:

- `apk upgrade` applied 286 published updates, including kernel generation 82
  and its kmods.
- `apk add konsole` installed Konsole 26.08.3-r2 and its 82 dependencies
  (Qt Quick/Multimedia/TextToSpeech/Wayland, KF6, Breeze Icons, Hunspell,
  Flite, fcitx5-qt).
- Running kernel remained `7.3.5-81-openwrt`; `/etc/openwrt-kernel` records
  `7.3.5-82-openwrt` as default with the 3-attempt counter and
  `7.3.5-81-openwrt` as fallback. No reboot was performed.
- The APK post-commit hook re-synced `/etc/apk/repositories.d/lan-local.list`;
  `uci-history` recorded revision 91 with no UCI change.

### Icon theme follow-up

The first installation exposed that `kf6-kiconthemes` had been built with
`USE_BreezeIcons=OFF`, which makes `KIconTheme::initTheme()` a no-op. Konsole
therefore stayed on Qt's `hicolor` theme and many Configure Konsole icons were
missing. `kf6-kiconthemes` r2 now builds `USE_BreezeIcons=ON`, and
`kf6-breeze-icons` r2 adds aliases for `view-split-auto` and
`org.gnome.gedit` and inherits Adwaita after hicolor.

Both r2 packages were published in snapshot
`/srv/openwrt-feeds/public/snapshots/20261122T004638.434359Z` and installed on
the router. A probe in the live GNOME Wayland session reports theme
`KIconEngine`, fallback `breeze`, and zero missing icons from Konsole's set.
Restarting Konsole is enough; no reboot is needed for the icon fix.
