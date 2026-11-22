# On-device Qt 6 development

The router can compile its own C++ Qt 6 applications. The development files
are packaged separately from the runtime libraries so normal images and
updates do not carry headers or build tools.

## Install

```sh
apk add qt6base-dev
```

`qt6base-dev` depends on `native-libs-dev`, which supplies the common
graphics and system headers that Qt applications and Qt itself need:
Xlib/XCB, OpenGL/EGL, GBM, libdrm, ALSA, xkbcommon, Wayland client/server,
HarfBuzz, FreeType and Fontconfig.

## What is installed

| Path | Contents |
| --- | --- |
| `/usr/include/qt6` | Qt Core, Gui, Widgets, Network, DBus, Xml, PrintSupport, Concurrent and Test headers |
| `/usr/lib/cmake/Qt6*` | Qt CMake packages and host-tool packages |
| `/usr/lib/pkgconfig/Qt6*.pc` | pkg-config metadata |
| `/usr/lib/qt6/mkspecs` | qmake specs, including `linux-openwrt-g++` |
| `/usr/lib/qt6/libexec` | `moc`, `uic`, `rcc` and the auxiliary Qt tools |
| `/usr/bin` | `moc`, `uic`, `rcc`, `qmake6`, `qmake`, `qtpaths6`, `qt-cmake` |

The tools are built for x86_64 and use the target Qt libraries already
installed under `/usr/lib`.

## pkg-config

```sh
g++ -std=c++17 $(pkg-config --cflags Qt6Widgets) main.cpp \
    $(pkg-config --libs Qt6Widgets) -o myapp
```

## CMake

```cmake
cmake_minimum_required(VERSION 3.16)
project(myapp LANGUAGES CXX)
set(CMAKE_CXX_STANDARD 17)
set(CMAKE_AUTOMOC ON)
find_package(Qt6 REQUIRED COMPONENTS Widgets)
add_executable(myapp main.cpp)
target_link_libraries(myapp PRIVATE Qt6::Widgets)
```

```sh
cmake -S . -B build
cmake --build build
```

`qt-cmake` is a small wrapper around `cmake` and can be used instead of
`cmake -S`.

## qmake

```sh
qmake6 myapp.pro
make
```

`qmake6` uses the `linux-openwrt-g++` target spec and the installed host
tools.

## Scope

The package covers Qt Base. Qt Quick/QML, Qt Multimedia, Qt TextToSpeech and
Qt Wayland development files are not included; those modules are currently
installed only as runtime packages for the desktop and Konsole. KDE
Frameworks headers and CMake files are likewise not part of this package.
