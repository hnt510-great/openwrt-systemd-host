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
router's installed packages still carry their original r1/r5 versions; feed
publication of the rebuilt bytes is a separate step.

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
| Before the module rebuild, a Qt Quick app crashed under Wayland with SIGSEGV; afterwards it runs | passed |
| A Qt Widgets app runs under Wayland and under XWayland/xcb | passed |
| A `QtQuick.Controls.Basic` app with `ProgressBar`, `StackView`, `BusyIndicator`, `RangeSlider` and `CalendarModel` builds and runs | passed |
| `QtQuick/Controls/Basic` contains the 69 QML/JS/plugin/metadata files, including `StackView.qml` and `ProgressBar.qml` | passed |
| Full rebuild of Qt Declarative with OpenGL | passed |
| GUI execution: Qt Quick, Widgets and Basic controls under Wayland and xcb | passed |

## Evidence

- Build logs, manual package staging and the router APK set:
  `/srv/openwrt-validation/qt6-dev-packages-20261122/`
- Feed changes are mirrored in `patches/feeds/0050-video-qt6-desktop.patch`;
  the fragment is `configs/qt6-dev.config`.
- Router test artifacts: `/tmp/qtsql-test.cpp`, `/tmp/qmlcheck.qml`,
  `/tmp/qtcmake` and `/tmp/qtquicktest`.
