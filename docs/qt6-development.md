# On-device Qt 6 development

The router can compile its own C++ Qt 6 applications and run the Qt QML and
Linguist command-line tools. The development files are packaged separately
from the runtime libraries so normal images and updates do not carry headers
or build tools.

## Install

```sh
apk add qt6base-dev qt6quick-dev qt6svg-dev qt6multimedia-dev \
    qt6speech-dev qt6waylandclient-dev qt6quick-tools qt6tools
```

`qt6quick-dev` pulls `qt6quick-tools` and `qt6base-dev`; the other module
development packages pull `qt6base-dev` as well. `qt6base-dev` depends on
`native-libs-dev`, which supplies the common graphics and system headers that
Qt applications and Qt itself need: Xlib/XCB, OpenGL/GLES2/EGL, GBM, libdrm,
ALSA, xkbcommon, Wayland client/server, HarfBuzz, FreeType and Fontconfig.

The opt-in `configs/qt6-dev.config` fragment selects all of these packages and
also enables the Qt SQL and OpenGL ES build options:

```sh
./scripts/kconfig.pl + .config configs/qt6-dev.config > .config.new
mv .config.new .config
make defconfig
```

## What is installed

| Path | Contents |
| --- | --- |
| `/usr/include/qt6` | Qt Core, Gui, Widgets, Network, DBus, Xml, PrintSupport, Concurrent, Test, Sql and OpenGL headers; Qml, Quick, Quick Controls, Labs, Svg, Multimedia, TextToSpeech and Wayland client headers |
| `/usr/lib/cmake/Qt6*` | Qt CMake packages for the installed modules, including `Qt6QmlTools` |
| `/usr/lib/pkgconfig/Qt6*.pc` | pkg-config metadata |
| `/usr/lib/qt6/mkspecs` | qmake specs, including `linux-openwrt-g++` |
| `/usr/lib/qt6/libexec` | `moc`, `uic`, `rcc`, `qtwaylandscanner`, `qmlcachegen`, `qmltyperegistrar`, `qmlimportscanner`, `qmljsrootgen` and `qmlaotstats` |
| `/usr/lib/qt6/metatypes` | Qt module metatypes JSON used by CMake and the meta-object tools |
| `/usr/bin` | `moc`, `uic`, `rcc`, `qmake6`, `qmake`, `qtpaths6`, `qt-cmake` |
| `/usr/bin` | `qml`, `qmlscene`, `qmltestrunner`, `qmleasing`, `qmllint`, `qmlformat`, `qmldom`, `qmltc`, `qmlplugindump`, `qmlprofiler`, `qmltime` |
| `/usr/bin` | `lupdate`, `lrelease`, `lconvert` |

The tools are built for x86_64 and use the target Qt libraries already
installed under `/usr/lib`. `moc`, `uic`, `rcc`, `qmllint`, `qmlformat`,
`qmldom`, `qmltc`, `qmlplugindump`, `qmlprofiler`, `qmltime`, `lupdate` and
`lrelease` are host-built binaries; this is the same mechanism `qt6base-dev`
already uses for `moc`. `qml`, `qmlscene`, `qmltestrunner` and `qmleasing` are
target builds from Qt Declarative.

## C++

```sh
g++ -std=c++17 $(pkg-config --cflags Qt6Widgets) main.cpp \
    $(pkg-config --libs Qt6Widgets) -o myapp
```

```cmake
cmake_minimum_required(VERSION 3.16)
project(myapp LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_AUTOMOC ON)
find_package(Qt6 REQUIRED COMPONENTS Quick)
add_executable(myapp main.cpp)
target_link_libraries(myapp PRIVATE Qt6::Quick)
```

```sh
cmake -S . -B build
cmake --build build
```

`qt-cmake` is a small wrapper around `cmake` and can be used instead of
`cmake -S`.

```sh
qmake6 myapp.pro
make
```

`qmake6` uses the `linux-openwrt-g++` target spec and the installed host
tools.

## QML

`qml` and `qmlscene` run QML applications; they need a QPA platform plugin
from the running desktop session. `qmllint`, `qmlformat`, `qmldom` and
`qmltc` work without a display:

```sh
qmllint main.qml
qmlformat -i main.qml
qml main.qml
qmlscene main.qml
```

`qmlplugindump`, `qmlprofiler` and `qmltime` are included for module and
performance inspection. `qmltestrunner` runs QML test cases. The QML
build-time helpers (`qmlcachegen`, `qmltyperegistrar`, `qmlimportscanner`,
`qmljsrootgen` and `qmlaotstats`) live in `/usr/lib/qt6/libexec` and are used
by `qt_add_qml_module`. QML module source files are installed even when the
module's `qmldir` has a `prefer` line; qmlcachegen and the on-device tooling
need them on disk. The QML plugin CMake target files are omitted because
the runtime image installs only a subset of the QML modules; Qt loads modules
by path at runtime.

Qt Quick uses the OpenGL RHI on Wayland. The Qt Base build enables OpenGL ES2
and EGL but not desktop GL (GLX), so under XWayland/xcb the RHI cannot create
its OpenGL context. Use the software backend there:

```sh
QT_QPA_PLATFORM=xcb QT_QUICK_BACKEND=software qml main.qml
```

Qt Widgets applications are unaffected and run under both Wayland and xcb.

## SQL and OpenGL

With `CONFIG_BUILD_qt6base_SQL=y` the build includes QtSql and its SQLite
driver:

```sh
apk add qt6base-sql qt6base-plugin-sqldrivers-sqlite
```

The driver uses Qt's bundled SQLite; `QSqlDatabase::drivers()` reports
`QSQLITE`. The Qt SQL headers and CMake packages are part of `qt6base-dev`,
so no separate `qt6sql-dev` package exists. The same applies to OpenGL:
`qt6base-dev` carries the QtOpenGL and QtOpenGLWidgets development files when
`CONFIG_BUILD_qt6base-gui_OPENGL_OPENGLES2=y` is selected, with the runtime in
`qt6base-opengl` and `qt6base-openglwidgets`.

## Translations

```sh
lupdate myapp.pro -ts translations/zh_CN.ts
lrelease translations/zh_CN.ts
lconvert -i translations/zh_CN.ts -o translations/zh_CN.qm
```

## Python bindings

PySide6 is not part of the feed. The upstream manylinux wheels bundle their
own Qt libraries and can be installed with pip once `python3-pip` is present:

```sh
pip install PySide6-Addons
```

`PySide6-Addons` adds the Qt Multimedia, Qt WebEngine, Qt PDF and other
optional bindings and is several hundred megabytes. It installs into the
system Python site-packages; use a virtual environment when disk space is
limited. The bindings do not use the distribution Qt packages from this feed.

## Scope

The packages cover the public development files of Qt Base, Qt Declarative,
Qt Svg, Qt Multimedia, Qt TextToSpeech and Qt Wayland Client. Qt Designer and
the Qt Linguist GUI application are not built; the command-line Linguist tools
are. KDE Frameworks headers and CMake files are likewise not part of these
packages.

See `docs/qt6-development-validation.md` for the validation record.
