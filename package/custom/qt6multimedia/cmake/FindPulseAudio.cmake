# CMake 4 removed the bundled FindPulseAudio module. Qt Multimedia still calls
# find_package(PulseAudio), so provide the same variables from pkg-config.
find_package(PkgConfig QUIET)
if(PKG_CONFIG_FOUND)
    pkg_check_modules(PC_PULSEAUDIO QUIET libpulse)
endif()

find_path(PULSEAUDIO_INCLUDE_DIR
    NAMES pulse/pulseaudio.h
    HINTS ${PC_PULSEAUDIO_INCLUDEDIR} ${PC_PULSEAUDIO_INCLUDE_DIRS})
find_library(PULSEAUDIO_LIBRARY
    NAMES pulse
    HINTS ${PC_PULSEAUDIO_LIBDIR} ${PC_PULSEAUDIO_LIBRARY_DIRS})

include(FindPackageHandleStandardArgs)
find_package_handle_standard_args(PulseAudio DEFAULT_MSG
    PULSEAUDIO_LIBRARY PULSEAUDIO_INCLUDE_DIR)

mark_as_advanced(PULSEAUDIO_INCLUDE_DIR PULSEAUDIO_LIBRARY)
