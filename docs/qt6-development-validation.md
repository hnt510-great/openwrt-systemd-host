# Qt 6 on-device development validation record

Date: 2026-11-22

## Scope

Optional Qt 6 Base, Quick/QML, SVG, Multimedia, TextToSpeech and Wayland
client development packages, the QML and Linguist command-line tools, and the
Qt SQL/OpenGL build options on the x86/64 glibc systemd router. Qt Base was
built with SQL and OpenGL ES enabled. The packages were installed on the
router; no image was built or flashed. The Qt Base rebuild changed the OpenGL
configuration, so the Qt Declarative, Svg, Multimedia, TextToSpeech and
Wayland client modules were rebuilt and reinstalled against the new base. The
rebuilt packages were published to the LAN feed as Qt Base r6 and module r2,
and the router was upgraded from that feed; no image was built or flashed.

## Checks

| Check | Result |
| --- | --- |
| `native-libs-dev` 1-r13 builds and provides X11/XCB/GL/GLES2/GLES3/EGL/KHR/GBM/libdrm/ALSA/xkbcommon/Wayland/HarfBuzz/FreeType/Fontconfig headers | passed |
| `native-libs-dev` 1-r13 provides the `libGL`, `libOpenGL`, `libGLESv2`, `libEGL`, `libdrm`, `libxkbcommon`, `libwayland-*` linker names and the matching `.pc` files | passed |
| `qt6base-dev` 6.9.3-r5 builds with Qt Base headers, CMake and pkg-config metadata | passed |
| `qt6base` 6.9.3-r5 builds with `CONFIG_BUILD_qt6base_SQL=y` | passed |
| `qt6base-sql` contains `libQt6Sql.so.6.9.3`; `qt6base-plugin-sqldrivers-sqlite` contains `libqsqlite.so` | passed |
| `qt6base` builds with `CONFIG_BUILD_qt6base-gui_OPENGL_OPENGLES2=y`; `qt6base-opengl` and `qt6base-openglwidgets` contain their runtime libraries | passed |
| `qt6base-dev` contains `QtSql`, `QtOpenGL` and `QtOpenGLWidgets` headers, CMake packages and `.pc` files | passed |
| `qt6quick-dev`, `qt6quick-tools`, `qt6svg-dev`, `qt6multimedia-dev`, `qt6speech-dev`, `qt6waylandclient-dev` and `qt6tools` APKs install on the router | passed |
| `qmllint 6.9.3` lints a QML file without errors | passed |
| `lrelease` and `qmlformat` report version 6.9.3; `qml`, `qmlscene` and `qmltestrunner` exist | passed |
| `pkg-config --modversion` reports 6.9.3 for Qt6Quick, Qt6Qml, Qt6Sql, Qt6OpenGL, Qt6Multimedia, Qt6TextToSpeech, Qt6WaylandClient and Qt6Svg | passed |
| A QtSql program loads the `QSQLITE` driver on the router | passed |
| CMake `find_package(Qt6 COMPONENTS Core Gui Widgets Quick Qml Sql OpenGL OpenGLWidgets Svg Multimedia TextToSpeech WaylandClient)` configures on the router | passed |
| QML build helpers (`qmlcachegen`, `qmltyperegistrar`, `qmlimportscanner`, `qmljsrootgen`, `qmlaotstats`), the `Qt6QmlTools` CMake package and the module metatypes JSON files are present | passed |
| A CMake Qt Quick project using `qt_add_qml_module` configures and builds on the router, including qmlcachegen and qmltyperegistrar | passed |
| `wayland-scanner 1.26.0` is installed and found by CMake | passed |
| Qt module libraries all match the rebuilt base library timestamps (base 11:31, modules 12:10) | passed |
| LAN feed snapshot `20261122T052658.620916Z` publishes Qt Base r6 and the module r2 packages; upgrade receipt status is `passed` | passed |
| Router upgraded from the LAN feed to Qt Base 6.9.3-r6 and module 6.9.3-r2 | passed |
| Before the module rebuild, a Qt Quick app crashed under Wayland with SIGSEGV; afterwards it runs | passed |
| A Qt Widgets app runs under Wayland and under XWayland/xcb | passed |
| Qt Quick under xcb needs `QT_QUICK_BACKEND=software` because the base build has GLES2/EGL but no desktop GL; with it the app runs | passed |
| A `QtQuick.Controls.Basic` app with `ProgressBar`, `StackView`, `BusyIndicator`, `RangeSlider` and `CalendarModel` builds and runs | passed |
| `QtQuick/Controls/Basic` contains the 69 QML/JS/plugin/metadata files, including `StackView.qml` and `ProgressBar.qml` | passed |
| Full rebuild of Qt Declarative with OpenGL | passed |
| GUI execution: Qt Quick, Widgets and Basic controls under Wayland and xcb | passed |

## Evidence

- Build logs, manual package staging and the router APK set:
  `/srv/openwrt-validation/qt6-dev-packages-20261122/`
- Feed changes are mirrored in `patches/feeds/0050-video-qt6-desktop.patch`;
  the fragment is `configs/qt6-dev.config`.
- Publication receipt: `/srv/openwrt-feeds/upgrade-receipts/1795325267681290414.json`;
  current snapshot `20261122T052658.620916Z`.
- Router test artifacts: `/tmp/qtsql-test.cpp`, `/tmp/qmlcheck.qml`,
  `/tmp/qtcmake` and `/tmp/qtquicktest`.

## 2026-11-25 Qt 6.11.3 Charts, PIE, CMake, prefix, and plugins update

### Scope

Added `qt6charts` / `qt6charts-dev` (Qt 6.11.3), enabled `--enable-default-pie`
on the on-device native `gcc` (`15.3.0-r15`), fixed Qt 6.11.3 PIE/PIC dev
flags, missing CMake tool binaries (`wasmdeployqt`, `qmlcontextpropertydump`),
dangling CMake/pkg-config entries and missing `.so` linker symlinks, set
`-DFEATURE_relocatable=OFF` so `QLibraryInfo` resolves `/usr`, enabled
`libqico.so`, and installed `qt6translations`, `offscreen`/`minimal` QPA
plugins, and `jpeg`/`gif` imageformat plugins via the LAN APK feed on
`192.0.2.1`. No firmware image was built or flashed; no VM run was required
beyond host package audits and live physical-router testing.

### Checks

| Check | Result |
| --- | --- |
| Host audit of 1,512 Qt6 CMake files across all 7 `qt6*-dev` packages reports 0 missing `IMPORTED_LOCATION` targets | passed |
| Host audit of 58 `Qt6*.pc` files reports 0 missing `.so` linker symlinks | passed |
| `python3 scripts/tests/test-custom-package-updates.py` (58 tests) | passed |
| Coordinated LAN feed publication preflight (1,609 packages, 3,317 ELF files) and promotion to snapshot `20261125T144928.142367Z` | passed |
| Physical router (`192.0.2.1`) `apk upgrade` (72 packages) and `apk add` (`qt6charts`, `qt6charts-dev`, `qt6translations`, `jpeg`/`gif` plugins) | passed |
| Default `g++` + `pkg-config` (`Qt6Widgets`, `Qt6Charts`, `Qt6Multimedia`, `Qt6MultimediaWidgets`, `Qt6TextToSpeech`, `Qt6WaylandClient`, `Qt6QmlCompiler`) builds `ET_DYN` PIE and `QTimer::timeout` `connect()` fires | passed |
| `qmake6` default mkspec (`QT += widgets charts`) builds `ET_DYN` PIE and `QTimer::timeout` `connect()` fires | passed |
| CMake `find_package(Qt6 REQUIRED COMPONENTS Core Gui Widgets Quick Qml Charts ChartsQml Svg Multimedia MultimediaWidgets TextToSpeech WaylandClient Sql OpenGL OpenGLWidgets)` configures, builds `ET_DYN` PIE, and `QTimer::timeout` fires | passed |
| `QLibraryInfo` reports `PrefixPath=/usr`, `TranslationsPath=/usr/share/qt6/translations`, and `qtbase_zh_CN.qm` loads | passed |
| `QImageReader::supportedImageFormats()` reports `jpeg`, `gif`, and `ico`; `QT_QPA_PLATFORM=offscreen` and `minimal` both run cleanly | passed |

### Evidence

- Published snapshot: `/srv/openwrt-feeds/public/snapshots/20261125T144928.142367Z`.
- Feed mirrors: `patches/feeds/0054-packages-gcc-default-pie.patch`,
  `patches/feeds/0055-video-qt6-dev-fixes.patch`, and
  `configs/qt6-dev-fixes-feeds.json`.
