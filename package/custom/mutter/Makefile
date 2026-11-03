include $(TOPDIR)/rules.mk

PKG_NAME:=mutter
PKG_VERSION:=51.1
PKG_RELEASE:=1
PKG_SOURCE:=mutter-51.1.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/mutter/51/
PKG_HASH:=0d311d87901dbcb94518fb89304febe30852ce5d8a4befa9f87e85c68eceefde
PKG_LICENSE:=LGPL-2.1-or-later
PKG_BUILD_DEPENDS:=wayland/host wayland-protocols libxcvt/host
GNOME_TITLE:=GNOME Wayland compositor
GNOME_DEPENDS:=+glib2-gir +libgraphene +pixman +gsettings-desktop-schemas +libxkbcommon +at-spi2-core +colord +liblcms2 +libei +libdisplay-info +libdrm +libpango +harfbuzz +fribidi +libX11 +libXcomposite +libXcursor +libXdamage +libXext +libXfixes +libXi +xkeyboard-config +libXrandr +libxcb +libXinerama +libXau +gnome-desktop +libcanberra +libmesa +libwayland +libsystemd +libudev-systemd +libgudev +libinput +libwacom +libstartup-notification +libpipewire +xwayland
GNOME_MESON_ARGS:=-Dremote_desktop=true -Dxwayland=true -Dxwayland_path=/usr/bin/Xwayland -Dintrospection=true -Dprofiler=false -Dtests=disabled -Dcogl_tests=false -Dclutter_tests=false -Dmutter_tests=false -Dinstalled_tests=false -Ddocs=false -Ddevkit=disabled -Dbash_completion=false

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
