include $(TOPDIR)/rules.mk

PKG_NAME:=gtk4
PKG_VERSION:=4.24.2
PKG_RELEASE:=1
PKG_SOURCE:=gtk-4.24.2.tar.xz
PKG_SOURCE_URL:=https://download.gnome.org/sources/gtk/4.24/
PKG_HASH:=05561abc25d1b1400136bf79ab68830cb4b053d1922ae97e551b3f19755bf3cb
PKG_LICENSE:=LGPL-2.1-or-later
PKG_BUILD_DIR:=$(BUILD_DIR)/gtk-$(PKG_VERSION)
PKG_BUILD_DEPENDS:=wayland/host wayland-protocols libxml2/host
GNOME_TITLE:=GTK4 Wayland and X11 toolkit
GNOME_DEPENDS:=+libX11 +libXrender +libXi +libXext +libXrandr +libXcursor +libXdamage +libXfixes +libXinerama +iso-codes +glib2-gir +libgraphene +libpango +libgdk-pixbuf +libcairo +libepoxy +libwayland +libxkbcommon +libmesa +libjpeg +libpng +libtiff +libdrm +fontconfig +libintl-full
GNOME_MESON_ARGS:=-Dx11-backend=true -Dwayland-backend=true -Dbroadway-backend=false -Dvulkan=disabled -Dmedia-gstreamer=disabled -Dprint-cups=disabled -Dprint-cpdb=disabled -Dcloudproviders=disabled -Dtracker=disabled -Dcolord=disabled -Dsysprof=disabled -Daccesskit=disabled -Dintrospection=enabled -Ddocumentation=false -Dman-pages=false -Dbuild-tests=false -Dbuild-testsuite=false -Dbuild-examples=false -Dbuild-demos=false

include $(INCLUDE_DIR)/gnome-package.mk

$(eval $(call BuildPackage,$(PKG_NAME)))
