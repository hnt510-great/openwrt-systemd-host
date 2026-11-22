# Qt 6 on-device development validation record

Date: 2026-11-22

## Scope

Optional `qt6base-dev` and `native-libs-dev` packages installed on the
x86/64 glibc systemd router. No image was built or flashed for this record.
The checks compile Qt applications on the router; they do not run a GUI
session or exercise every Qt module.

## Checks

| Check | Result |
| --- | --- |
| `native-libs-dev` 1-r12 builds with X11/XCB/OpenGL/EGL/GBM/libdrm/ALSA/xkbcommon/Wayland/HarfBuzz/FreeType/Fontconfig headers | passed |
| `qt6base-dev` 6.9.3-r5 builds with Qt Base headers, CMake and pkg-config metadata | passed |
| `/usr/bin/moc`, `uic`, `rcc` and `qmake6` exist and report version 6.9.3 | passed |
| `pkg-config --modversion Qt6Widgets` reports 6.9.3; direct `g++` build links | passed |
| qmake project with `QT += widgets` configures and builds | passed |
| CMake project with `find_package(Qt6 COMPONENTS Widgets)` configures and builds | passed |
| CMake AUTOMOC project with a `Q_OBJECT` class builds `moc_thing.cpp` | passed |
| Package installation does not overwrite pkg-config files owned by the graphics runtime packages | passed |
| Router installation left the running kernel and services untouched | passed |

## Evidence

- Build logs: `/srv/openwrt-validation/konsole-port/native-libs-dev-r12.log`,
  `qt6base-dev4.log`
- Router test projects: `/tmp/qthello` (CMake), `/tmp/qthello-qmake` (qmake),
  `/tmp/qtmoc2` (AUTOMOC); logs `/tmp/qthello-cmake2.log`,
  `/tmp/qmake2.log`, `/tmp/qtmoc2.log`
- Feed changes are mirrored in `patches/feeds/0050-video-qt6-desktop.patch`;
  the fragment is `configs/qt6-dev.config`.
